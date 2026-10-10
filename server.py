#!/usr/bin/env python3
"""PR Pilot — fila única do Azure DevOps (várias organizações/contas): PRs, aprovações de release e
permissões de pipeline, com regras de automação e uma tela local. Roda só na sua máquina.

Dados locais por usuário (macOS: ~/Library/Application Support/PR Pilot; PR_PILOT_DATA muda o lugar):
  config.json    organizações + PATs (chmod 600, editado pela tela Ambiente)
  rules.json     regras de automação + ajustes (editados pela tela)
  archive.json   PRs arquivadas/ignoradas
  notified.json  itens já notificados (não repete notificação)
  activity.jsonl histórico de votos e ações
"""
import base64
import fnmatch
import json
import os
import re
import shutil
import sys
import webbrowser
import statistics
import subprocess
import threading
import time
import urllib.error
import uuid
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))


def default_data_dir():
    # Um lugar só por usuário: o app, o ▶ do editor e o terminal enxergam as mesmas contas e regras.
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/PR Pilot")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PR Pilot")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "pr-pilot")


DATA = os.path.abspath(os.environ.get("PR_PILOT_DATA") or default_data_dir())
os.makedirs(DATA, exist_ok=True)
for _old in (BASE, os.path.join(BASE, "data")):
    # versões antigas guardavam os dados na raiz do projeto e depois em ./data
    for _name in ("config.json", "rules.json", "archive.json", "notified.json", "activity.jsonl"):
        if os.path.exists(os.path.join(_old, _name)) and not os.path.exists(os.path.join(DATA, _name)) and _old != DATA:
            shutil.move(os.path.join(_old, _name), os.path.join(DATA, _name))
CONFIG_FILE = os.path.join(DATA, "config.json")
RULES_FILE = os.path.join(DATA, "rules.json")
ARCHIVE_FILE = os.path.join(DATA, "archive.json")
NOTIFIED_FILE = os.path.join(DATA, "notified.json")
ACTIVITY_FILE = os.path.join(DATA, "activity.jsonl")
UI_FILE = os.path.join(BASE, "index.html")
DEFAULT_PORT = 47821  # porta incomum de propósito: não briga com APIs/fronts locais
API = "api-version=7.0"
API_PREVIEW = "api-version=7.1-preview.1"
ACTIONS = ("approve", "archive", "notify")
DEPLOY_KINDS = ("release", "permission")
DEPLOY_ACTIONS = ("approve", "notify")

DEFAULT_SETTINGS = {
    "paused": False,          # pausa só as ações automáticas; a tela continua funcionando
    "notifyPending": True,    # notificação do macOS para PR nova esperando o meu voto
    "notifyAuto": True,       # notificação quando o piloto aprova sozinho
    "resurfaceOnPush": True,  # PR arquivada volta para a fila se receber push novo
    "notifyDeploys": True,    # notificação para release/permissão nova esperando você
}
# Regra: listas vazias = "qualquer". targets vazio = qualquer branch NÃO protegida.
DEFAULT_RULES = {
    "protectedTargets": ["master", "main"],
    "settings": DEFAULT_SETTINGS,
    "rules": [],
    "deployRules": [],
}

lock = threading.RLock()
wake = threading.Event()
state = {"prs": [], "errors": {}, "lastPoll": None, "me": {}, "pollMs": None,
         "deploys": [], "releases": [], "deployErrors": {}, "lastDeployPoll": None}
build_cache = {}      # (org, buildId) -> {"message", "requestedFor", "branch", ...} — dado imutável do build
deploy_failures = {}  # key -> ts da última falha automática (não insiste a cada ciclo)
analytics_cache = {}  # org -> {"at": ts, "prs": [...]} (PRs concluídas)


def now():
    return datetime.now(timezone.utc)


def now_iso():
    return now().isoformat(timespec="seconds")


def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def pr_key(org, pr_id):
    return f"{org}|{pr_id}"


def pr_summary(pr):
    return {k: pr.get(k) for k in ("org", "prId", "title", "creatorName", "creatorUnique", "target", "repo", "url", "created")}


def log_activity(by, action, pr, vote=None, detail=None, rule_id=None):
    entry = {"ts": now_iso(), "by": by, "action": action, "vote": vote, "detail": detail, "ruleId": rule_id,
             **pr_summary(pr)}
    with lock, open(ACTIVITY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['ts']}] {by} {action} {pr['org']} #{pr['prId']} {pr['title']}", flush=True)


def log_deploy(by, action, item, detail=None, rule_id=None):
    entry = {"ts": now_iso(), "by": by, "action": action, "detail": detail, "ruleId": rule_id, "kind": item["kind"],
             "org": item["org"], "title": item["title"], "pipeline": item["pipeline"], "stage": item.get("stage"),
             "branch": item.get("branch"), "version": item.get("version"), "prNumber": item.get("prNumber"),
             "url": item["url"], "prId": None}
    with lock, open(ACTIVITY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['ts']}] {by} {action} {item['org']} {item['title']}", flush=True)


def read_activity(limit=None):
    try:
        with open(ACTIVITY_FILE, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    if limit:
        lines = lines[-limit:]
    out = []
    for line in reversed(lines):
        if not line.strip():
            continue
        e = json.loads(line)
        e.setdefault("action", "vote")  # entradas antigas só registravam votos
        out.append(e)
    return out


def notify(title, subtitle, message):
    def q(s):
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = f"display notification {q(message)} with title {q(title)} subtitle {q(subtitle)}"
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
    except Exception:  # noqa: BLE001 — notificação nunca derruba o ciclo
        pass


class Org:
    def __init__(self, cfg):
        self.name = cfg["name"]
        self.url = cfg["url"].rstrip("/")
        self.cfg = cfg
        self._pat = None
        self.me = None
        self.vsrm = self.url.replace("://dev.azure.com", "://vsrm.dev.azure.com")

    def pat(self):
        if self._pat is None:
            if self.cfg.get("pat"):
                self._pat = self.cfg["pat"]
            elif self.cfg.get("patCommand"):
                self._pat = subprocess.run(self.cfg["patCommand"], shell=True, capture_output=True,
                                           text=True, check=True).stdout.strip()
            if not self._pat:
                raise RuntimeError("PAT não configurado (config.json)")
        return self._pat

    def req(self, method, path, body=None):
        url = path if path.startswith("http") else f"{self.url}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header("Authorization", "Basic " + base64.b64encode(f":{self.pat()}".encode()).decode())
        r.add_header("Accept", "application/json")
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                # PAT inválido/expirado: o Azure responde 203 com a página HTML de login, não 401.
                if resp.status == 203 or "json" not in resp.headers.get("Content-Type", ""):
                    raise RuntimeError("PAT inválido ou expirado (Azure devolveu página de login)")
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"HTTP {e.code} em {method} {url}: {msg}") from None

    def identity(self):
        if self.me is None:
            u = self.req("GET", "_apis/connectionData")["authenticatedUser"]
            self.me = {"id": u["id"], "name": u.get("providerDisplayName", ""),
                       "email": (u.get("properties", {}).get("Account") or {}).get("$value", "")}
        return self.me

    def projects(self):
        return self.req("GET", f"_apis/projects?$top=500&{API}")["value"]

    def _shape(self, p, pr):
        creator = pr.get("createdBy", {})
        repo = pr["repository"]
        proj = urllib.parse.quote(p["name"])
        reviewers = [{"name": rv.get("displayName", ""), "vote": rv.get("vote", 0),
                      "required": rv.get("isRequired", False), "id": rv.get("id")}
                     for rv in pr.get("reviewers", [])]
        return {
            "org": self.name,
            "project": p["name"],
            "projectId": p["id"],
            "repo": repo["name"],
            "repoId": repo["id"],
            "prId": pr["pullRequestId"],
            "title": pr["title"],
            "description": (pr.get("description") or "")[:1500],
            "creatorName": creator.get("displayName", ""),
            "creatorUnique": creator.get("uniqueName", ""),
            "creatorId": creator.get("id"),
            "source": pr["sourceRefName"].removeprefix("refs/heads/"),
            "target": pr["targetRefName"].removeprefix("refs/heads/"),
            "isDraft": pr.get("isDraft", False),
            "created": pr.get("creationDate"),
            "closed": pr.get("closedDate"),
            "mergeStatus": pr.get("mergeStatus"),
            "commit": (pr.get("lastMergeSourceCommit") or {}).get("commitId"),
            "autoComplete": bool(pr.get("autoCompleteSetBy")),
            "reviewers": reviewers,
            "url": f"{self.url}/{proj}/_git/{urllib.parse.quote(repo['name'])}/pullrequest/{pr['pullRequestId']}",
        }

    def fetch_prs(self):
        me = self.identity()
        prs = []
        for p in self.projects():
            proj = urllib.parse.quote(p["name"])
            data = self.req("GET", f"{proj}/_apis/git/pullrequests?searchCriteria.status=active&$top=500&{API}")
            for raw in data["value"]:
                pr = self._shape(p, raw)
                if pr["creatorId"] == me["id"] or pr["isDraft"]:
                    continue  # minhas PRs e rascunhos ficam de fora
                pr["myVote"] = next((rv["vote"] for rv in pr["reviewers"] if rv["id"] == me["id"]), 0)
                pr["approvals"] = sum(1 for rv in pr["reviewers"] if rv["vote"] >= 5)
                prs.append(pr)
        with ThreadPoolExecutor(8) as ex:
            for pr, pol in zip(prs, ex.map(self.policies, prs)):
                pr["policies"] = pol
                pr["build"] = build_status(pol)
        return prs

    def policies(self, pr):
        artifact = urllib.parse.quote(f"vstfs:///CodeReview/CodeReviewId/{pr['projectId']}/{pr['prId']}", safe="")
        try:
            data = self.req("GET", f"{urllib.parse.quote(pr['project'])}/_apis/policy/evaluations"
                                   f"?artifactId={artifact}&api-version=7.0-preview.1")
        except Exception:  # noqa: BLE001 — sem permissão de policy, só não mostra
            return []
        out, seen = [], set()
        for ev in data.get("value", []):
            cfg = ev.get("configuration", {})
            if not cfg.get("isEnabled", True):
                continue
            name = (cfg.get("settings") or {}).get("displayName") or cfg.get("type", {}).get("displayName", "?")
            if (name, ev.get("status")) in seen:
                continue  # mesma policy configurada em mais de um escopo
            seen.add((name, ev.get("status")))
            out.append({
                "name": name,
                "type": cfg.get("type", {}).get("displayName", ""),
                "status": ev.get("status"),
                "blocking": cfg.get("isBlocking", False),
            })
        return out

    def fetch_completed(self, days):
        since = now() - timedelta(days=days)
        out = []
        for p in self.projects():
            proj = urllib.parse.quote(p["name"])
            data = self.req("GET", f"{proj}/_apis/git/pullrequests?searchCriteria.status=completed&$top=1000&{API}")
            for raw in data["value"]:
                closed = parse_dt(raw.get("closedDate"))
                if closed and closed >= since:
                    out.append(self._shape(p, raw))
        return out

    # ------------------------------------------------------------ releases / pipelines
    def build_info(self, project, build_id):
        ck = (self.name, int(build_id))
        if ck not in build_cache:
            b = self.req("GET", f"{urllib.parse.quote(project)}/_apis/build/builds/{build_id}?{API}")
            msg = (b.get("triggerInfo") or {}).get("ci.message")
            if not msg and b.get("sourceVersion") and (b.get("repository") or {}).get("type") == "TfsGit":
                try:
                    msg = self.req("GET", f"{urllib.parse.quote(project)}/_apis/git/repositories/{b['repository']['id']}"
                                          f"/commits/{b['sourceVersion']}?{API}").get("comment")
                except Exception:  # noqa: BLE001 — mensagem é só contexto
                    msg = None
            m = re.search(r"Merge pull request (\d+)", msg or "")
            build_cache[ck] = {
                "buildId": b["id"], "buildNumber": b.get("buildNumber"), "pipeline": b["definition"]["name"],
                "pipelineId": b["definition"]["id"], "branch": (b.get("sourceBranch") or "").removeprefix("refs/heads/"),
                "message": (msg or "").split("\n")[0][:200], "prNumber": int(m.group(1)) if m else None,
                "requestedFor": (b.get("requestedFor") or {}).get("displayName", ""), "queued": b.get("queueTime"),
                "repo": (b.get("repository") or {}).get("name"),
                "url": f"{self.url}/{urllib.parse.quote(project)}/_build/results?buildId={b['id']}",
            }
        return build_cache[ck]

    def fetch_deploys(self):
        me = self.identity()
        items, releases = [], []
        for p in self.projects():
            proj = urllib.parse.quote(p["name"])
            # 1) Release clássica esperando aprovação (pre/post deploy). Junta as minhas (inclui grupos) com as demais.
            mine = self.req("GET", f"{self.vsrm}/{proj}/_apis/release/approvals?statusFilter=pending&includeMyGroupApprovals=true"
                                   f"&assignedToFilter={urllib.parse.quote(me['email'] or me['id'])}&{API}")["value"]
            mine_ids = {a["id"] for a in mine}
            pending = {a["id"]: a for a in self.req("GET", f"{self.vsrm}/{proj}/_apis/release/approvals?statusFilter=pending&{API}")["value"]}
            pending.update({a["id"]: a for a in mine})
            rel_cache = {}
            for a in pending.values():
                rid = a["release"]["id"]
                if rid not in rel_cache:
                    rel_cache[rid] = self.req("GET", f"{self.vsrm}/{proj}/_apis/release/releases/{rid}?{API}")
                rel = rel_cache[rid]
                art = next((x for x in rel.get("artifacts", []) if x.get("isPrimary")), (rel.get("artifacts") or [{}])[0])
                ref = art.get("definitionReference", {})
                build = {}
                if ref.get("version", {}).get("id") and art.get("type") == "Build":
                    try:
                        build = self.build_info(p["name"], ref["version"]["id"])
                    except Exception:  # noqa: BLE001
                        build = {}
                env = a["releaseEnvironment"]
                items.append({
                    "kind": "release", "key": f"{self.name}|rel:{a['id']}", "org": self.name, "project": p["name"],
                    "approvalId": a["id"], "approvalType": a.get("approvalType"), "releaseId": rid, "releaseName": rel.get("name"),
                    "envId": env["id"],
                    "title": a["releaseDefinition"]["name"], "pipeline": a["releaseDefinition"]["name"], "stage": env["name"],
                    "branch": (ref.get("branch", {}).get("name") or build.get("branch") or "").removeprefix("refs/heads/"),
                    "version": ref.get("version", {}).get("name"), "buildId": build.get("buildId"),
                    "message": build.get("message"), "prNumber": build.get("prNumber"), "repo": build.get("repo"),
                    "requestedFor": build.get("requestedFor") or (rel.get("createdBy") or {}).get("displayName", ""),
                    "approver": (a.get("approver") or {}).get("displayName", ""), "mine": a["id"] in mine_ids,
                    "created": a.get("createdOn"), "resources": [],
                    "url": f"{self.url}/{proj}/_releaseProgress?_a=release-environment-logs&releaseId={rid}&environmentId={env['id']}",
                })
            # Um estágio com vários aprovadores gera uma aprovação por pessoa: fica uma linha, a minha quando houver.
            by_env = {}
            for it in [x for x in items if x["kind"] == "release" and x["project"] == p["name"]]:
                k = (it["releaseId"], it["envId"], it["approvalType"])
                if k not in by_env or (it["mine"] and not by_env[k]["mine"]):
                    by_env[k] = it
            others = [x["approver"] for x in items if x["kind"] == "release" and x["project"] == p["name"]]
            items = [x for x in items if x["kind"] != "release" or x["project"] != p["name"]] + list(by_env.values())
            for it in by_env.values():
                it["otherApprovers"] = sorted({a for a in others if a and a != it["approver"]})
            # 2) Aprovações de ambiente em pipeline YAML.
            try:
                yaml_appr = self.req("GET", f"{proj}/_apis/pipelines/approvals?state=pending&$expand=steps&{API_PREVIEW}")["value"]
            except Exception:  # noqa: BLE001 — recurso ausente em orgs antigas
                yaml_appr = []
            for a in yaml_appr:
                owner = (a.get("pipeline") or {}).get("owner") or {}
                build = self.build_info(p["name"], owner["id"]) if owner.get("id") else {}
                mine_step = any((st.get("assignedApprover") or {}).get("id") == me["id"] for st in a.get("steps", []))
                items.append({
                    "kind": "approval", "key": f"{self.name}|appr:{a['id']}", "org": self.name, "project": p["name"],
                    "approvalId": a["id"], "title": build.get("pipeline") or (a.get("pipeline") or {}).get("name", "?"),
                    "pipeline": build.get("pipeline") or (a.get("pipeline") or {}).get("name", "?"),
                    "stage": a.get("instructions") or "", "branch": build.get("branch"), "version": build.get("buildNumber"),
                    "buildId": build.get("buildId"), "pipelineId": build.get("pipelineId"), "message": build.get("message"),
                    "prNumber": build.get("prNumber"), "repo": build.get("repo"), "requestedFor": build.get("requestedFor"),
                    "mine": mine_step, "created": a.get("createdOn"), "resources": [], "url": build.get("url", self.url),
                })
            # 3) Runs travados pedindo permissão para usar recurso (grupo de variáveis, service connection, ambiente…).
            since = (now() - timedelta(days=30)).isoformat()
            runs = self.req("GET", f"{proj}/_apis/build/builds?statusFilter=notStarted,inProgress&$top=100&{API}")["value"]
            for b in (x for x in runs if (x.get("queueTime") or "") >= since[:19]):
                try:
                    timeline = self.req("GET", f"{proj}/_apis/build/builds/{b['id']}/timeline?{API}") or {}
                except Exception:  # noqa: BLE001
                    continue
                records = timeline.get("records") or []
                for cp in (r for r in records if r["type"] == "Checkpoint" and r["state"] == "inProgress"):
                    try:
                        suite = self.req("GET", f"{proj}/_apis/pipelines/checks/runs/{cp['id']}?$expand=1&{API_PREVIEW}")
                    except Exception:  # noqa: BLE001
                        continue
                    res = [c["checkConfigurationRef"]["resource"] for c in suite.get("checkRuns", [])
                           if c.get("status") == "running" and c["checkConfigurationRef"]["type"]["name"] == "Authorization"]
                    if not res:
                        continue
                    node = ((suite.get("context") or {}).get("GraphNode") or {}).get("Name")
                    stage = next((r["name"] for r in records if r["type"] == "Stage" and r.get("identifier") == node), node or "")
                    build = self.build_info(p["name"], b["id"])
                    items.append({
                        "kind": "permission", "key": f"{self.name}|perm:{b['id']}:{cp['id'][:8]}", "org": self.name,
                        "project": p["name"], "title": build["pipeline"], "pipeline": build["pipeline"],
                        "pipelineId": build["pipelineId"], "stage": stage, "branch": build["branch"],
                        "version": build["buildNumber"], "buildId": b["id"], "message": build["message"],
                        "prNumber": build["prNumber"], "repo": build["repo"], "requestedFor": build["requestedFor"],
                        "mine": True, "created": cp.get("startTime") or b.get("queueTime"),
                        "resources": [{"type": r["type"], "id": str(r["id"]), "name": r.get("name") or str(r["id"])} for r in res],
                        "url": build["url"],
                    })
            # Releases recentes, para acompanhar o que subiu.
            for r in self.req("GET", f"{self.vsrm}/{proj}/_apis/release/releases?$top=40&$expand=environments,artifacts&{API}")["value"]:
                art = next((x for x in r.get("artifacts", []) if x.get("isPrimary")), (r.get("artifacts") or [{}])[0])
                ref = art.get("definitionReference", {})
                releases.append({
                    "org": self.name, "id": r["id"], "name": r["name"], "pipeline": r["releaseDefinition"]["name"],
                    "created": r.get("createdOn"), "createdBy": (r.get("createdBy") or {}).get("displayName", ""),
                    "branch": (ref.get("branch", {}).get("name") or "").removeprefix("refs/heads/"),
                    "version": ref.get("version", {}).get("name"),
                    "envs": [{"name": e["name"], "status": e["status"]} for e in r.get("environments", [])],
                    "url": f"{self.url}/{proj}/_releaseProgress?_a=release-pipeline-progress&releaseId={r['id']}",
                })
        for it in items:
            if it.get("prNumber") and it.get("repo"):
                it["prUrl"] = f"{self.url}/{urllib.parse.quote(it['project'])}/_git/{urllib.parse.quote(it['repo'])}/pullrequest/{it['prNumber']}"
        return items, releases

    def decide_deploy(self, item, approve, comment=""):
        proj = urllib.parse.quote(item["project"])
        if item["kind"] == "release":
            self.req("PATCH", f"{self.vsrm}/{proj}/_apis/release/approvals/{item['approvalId']}?{API}",
                     {"status": "approved" if approve else "rejected", "comments": comment})
        elif item["kind"] == "approval":
            self.req("PATCH", f"{proj}/_apis/pipelines/approvals?{API_PREVIEW}",
                     [{"approvalId": item["approvalId"], "status": "approved" if approve else "rejected", "comment": comment}])
        elif item["kind"] == "permission":
            if approve:
                for r in item["resources"]:
                    self.req("PATCH", f"{proj}/_apis/pipelines/pipelinePermissions/{r['type']}/{urllib.parse.quote(r['id'], safe='')}?{API_PREVIEW}",
                             {"pipelines": [{"id": item["pipelineId"], "authorized": True}]})
            else:
                self.req("PATCH", f"{proj}/_apis/build/builds/{item['buildId']}?{API}", {"status": "cancelling"})

    def pr_approved_by_me(self, pr_id):
        pr = self.req("GET", f"_apis/git/pullrequests/{pr_id}?{API}")
        me = self.identity()
        return any(rv.get("id") == me["id"] and rv.get("vote", 0) >= 5 for rv in pr.get("reviewers", []))

    def vote(self, project, repo_id, pr_id, vote):
        me = self.identity()
        proj = urllib.parse.quote(project)
        self.req("PUT", f"{proj}/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}/reviewers/{me['id']}?{API}",
                 {"vote": vote})


def build_status(policies):
    builds = [p["status"] for p in policies if p["type"] == "Build"]
    if not builds:
        return "none"
    if "rejected" in builds or "broken" in builds:
        return "failed"
    if any(s in ("running", "queued") for s in builds):
        return "running"
    if all(s in ("approved", "notApplicable") for s in builds):
        return "ok"
    return "pending"


def load_orgs():
    cfg = load_json(CONFIG_FILE, {})
    return {o["name"]: Org(o) for o in cfg.get("orgs", []) if o.get("enabled", True)}, cfg


ORGS, CONFIG = load_orgs()


def reload_orgs():
    global ORGS, CONFIG
    orgs, cfg = load_orgs()
    with lock:
        ORGS, CONFIG = orgs, cfg
        state["prs"] = [p for p in state["prs"] if p["org"] in orgs]
        state["deploys"] = [d for d in state["deploys"] if d["org"] in orgs]
        state["releases"] = [r for r in state["releases"] if r["org"] in orgs]
        state["errors"], state["deployErrors"] = {}, {}
    analytics_cache.clear()
    wake.set()


def _as_list(v):
    if v is None:
        return []
    items = v if isinstance(v, list) else [v]
    return [str(i).strip() for i in items if str(i).strip() and str(i).strip() != "*"]


def normalize_rule(r):
    """Aceita o formato antigo (org/creator/target/repo/title como string) e o novo (listas)."""
    return {
        "id": r.get("id") or uuid.uuid4().hex[:8],
        "name": (r.get("name") or "").strip(),
        "enabled": bool(r.get("enabled", True)),
        "action": r.get("action") if r.get("action") in ACTIONS else "approve",
        "orgs": _as_list(r.get("orgs", r.get("org"))),
        "creators": _as_list(r.get("creators", r.get("creator"))),
        "targets": _as_list(r.get("targets", r.get("target"))),
        "repos": _as_list(r.get("repos", r.get("repo"))),
        "titleContains": (r.get("titleContains", r.get("title")) or "").strip(),
        "requireBuild": bool(r.get("requireBuild")),
    }


def normalize_deploy_rule(r):
    kind = r.get("kind") if r.get("kind") in DEPLOY_KINDS else "release"
    return {
        "id": r.get("id") or uuid.uuid4().hex[:8],
        "name": (r.get("name") or "").strip(),
        "enabled": bool(r.get("enabled", True)),
        "kind": kind,
        "action": r.get("action") if r.get("action") in DEPLOY_ACTIONS else "approve",
        "orgs": _as_list(r.get("orgs")),
        "pipelines": _as_list(r.get("pipelines")),
        "stages": _as_list(r.get("stages")) if kind == "release" else [],
        "branches": _as_list(r.get("branches")),
        "resources": _as_list(r.get("resources")) if kind == "permission" else [],
        "requirePrApproved": bool(r.get("requirePrApproved")) and kind == "release",
    }


def clean_rules(body):
    st = {**DEFAULT_SETTINGS, **{k: bool(v) for k, v in (body.get("settings") or {}).items() if k in DEFAULT_SETTINGS}}
    return {
        "protectedTargets": _as_list(body.get("protectedTargets", ["master", "main"])),
        "settings": st,
        "rules": [normalize_rule(r) for r in body.get("rules", [])],
        "deployRules": [normalize_deploy_rule(r) for r in body.get("deployRules", [])],
    }


def get_rules():
    raw = load_json(RULES_FILE, DEFAULT_RULES)
    r = clean_rules(raw)
    if r != raw:
        save_json(RULES_FILE, r)  # migra o formato antigo e fixa os ids
    return r


def glob_match(pattern, value):
    return fnmatch.fnmatchcase(value.lower(), (pattern or "*").strip().lower() or "*")


def target_matches(patterns, target, protected):
    target = target.lower()
    if not patterns:
        return target not in protected
    for pattern in patterns:
        pattern = pattern.lower()
        # Curinga nunca alcança branch protegida; para agir na master, a regra precisa dizer "master".
        if any(ch in pattern for ch in "*?[") and target in protected:
            continue
        if glob_match(pattern, target):
            return True
    return False


def rule_matches(r, pr, protected):
    if r["orgs"] and pr["org"] not in r["orgs"]:
        return False
    if r["creators"]:
        name, unique = pr["creatorName"].lower(), (pr.get("creatorUnique") or "").lower()
        if not any(c.lower() == unique or c.lower() in name for c in r["creators"]):
            return False
    if not target_matches(r["targets"], pr["target"], protected):
        return False
    if r["repos"] and not any(glob_match(x, pr["repo"]) for x in r["repos"]):
        return False
    if r["titleContains"] and r["titleContains"].lower() not in pr["title"].lower():
        return False
    return True


def protected_set(rules_cfg):
    return {t.strip().lower() for t in rules_cfg.get("protectedTargets", [])}


def matching_rule(pr, rules_cfg):
    protected = protected_set(rules_cfg)
    for idx, r in enumerate(rules_cfg.get("rules", [])):
        if r.get("enabled", True) and rule_matches(r, pr, protected):
            return idx
    return None


def text_match(patterns, value):
    """Sem curinga = parte do texto ("financeiro" pega "minhaempresa-financeiro-api - deploy"); com curinga = glob."""
    value = (value or "").lower()
    for pt in patterns:
        pt = pt.lower()
        if (any(ch in pt for ch in "*?[") and fnmatch.fnmatchcase(value, pt)) or (not any(ch in pt for ch in "*?[") and pt in value):
            return True
    return not patterns


def deploy_rule_matches(r, item):
    kind = "release" if item["kind"] in ("release", "approval") else "permission"
    if r["kind"] != kind or (r["orgs"] and item["org"] not in r["orgs"]):
        return False
    if not text_match(r["pipelines"], item["pipeline"]) or not text_match(r["stages"], item.get("stage")):
        return False
    if r["branches"] and not any(glob_match(b, item.get("branch") or "") for b in r["branches"]):
        return False
    # Permissão: a regra só libera se TODOS os recursos pedidos estiverem cobertos.
    if r["resources"] and not all(text_match(r["resources"], x["name"]) for x in item["resources"]):
        return False
    return True


def matching_deploy_rule(item, rules_cfg):
    return next((r for r in rules_cfg.get("deployRules", []) if r["enabled"] and deploy_rule_matches(r, item)), None)


def rule_label(rules_cfg, idx):
    r = rules_cfg["rules"][idx]
    return r["name"] or f"regra {idx + 1}"


def poll_once():
    started = time.monotonic()
    rules_cfg = get_rules()
    settings = rules_cfg["settings"]
    archive = load_json(ARCHIVE_FILE, {})
    notified = set(load_json(NOTIFIED_FILE, []))
    all_prs, errors, me, ok_orgs = [], {}, {}, set()

    for org in ORGS.values():
        try:
            prs = org.fetch_prs()
            me[org.name] = org.me
            ok_orgs.add(org.name)
        except Exception as e:  # noqa: BLE001 — uma org fora não derruba a outra
            errors[org.name] = str(e)
            with lock:
                all_prs.extend(p for p in state["prs"] if p["org"] == org.name)
            continue

        for pr in prs:
            key = pr_key(pr["org"], pr["prId"])
            arch = archive.get(key)
            if arch and settings["resurfaceOnPush"] and arch.get("commit") and pr["commit"] != arch["commit"]:
                archive.pop(key)
                arch = None
                log_activity("auto", "unarchive", pr, detail="novo push")
            pr["archived"] = arch is not None
            pr["rule"] = matching_rule(pr, rules_cfg)
            pr["waiting"] = None
            rule = rules_cfg["rules"][pr["rule"]] if pr["rule"] is not None else None
            pr["ruleId"] = rule["id"] if rule else None
            action = rule["action"] if rule else None

            if pr["archived"]:
                continue
            if action == "archive" and not settings["paused"]:
                archive[key] = {"ts": now_iso(), "commit": pr["commit"], "reason": rule_label(rules_cfg, pr["rule"]),
                                **pr_summary(pr)}
                pr["archived"] = True
                log_activity("auto", "archive", pr, detail=rule_label(rules_cfg, pr["rule"]), rule_id=rule["id"])
                continue
            if action == "approve" and pr["myVote"] == 0:
                if settings["paused"]:
                    pr["waiting"] = "pausado"
                elif rule.get("requireBuild") and pr["build"] not in ("ok", "none"):
                    pr["waiting"] = "build"
                else:
                    try:
                        org.vote(pr["project"], pr["repoId"], pr["prId"], 10)
                        pr["myVote"] = 10
                        pr["approvals"] += 1
                        log_activity("auto", "vote", pr, vote=10, detail=rule_label(rules_cfg, pr["rule"]), rule_id=rule["id"])
                        if settings["notifyAuto"]:
                            notify("PR Pilot — aprovada", f"{pr['org']} #{pr['prId']} · {pr['creatorName']} → {pr['target']}", pr["title"])
                    except Exception as e:  # noqa: BLE001
                        errors[org.name] = f"Falha ao auto-aprovar #{pr['prId']}: {e}"
                continue
            nkey = f"{key}|{pr['commit']}"
            if pr["myVote"] == 0 and nkey not in notified and (action == "notify" or settings["notifyPending"]):
                notified.add(nkey)
                if any(n.startswith(key + "|") for n in notified - {nkey}):
                    continue  # já avisei esta PR; push novo não renotifica
                notify("PR Pilot — aguardando seu voto", f"{pr['org']} #{pr['prId']} · {pr['creatorName']} → {pr['target']}", pr["title"])
        all_prs.extend(prs)

    # Arquivo e notificações só guardam PRs ainda ativas (das orgs lidas com sucesso).
    active = {pr_key(p["org"], p["prId"]) for p in all_prs}
    archive = {k: v for k, v in archive.items() if k in active or k.split("|")[0] not in ok_orgs}
    notified = {n for n in notified if "|".join(n.split("|")[:2]) in active or n.split("|")[0] not in ok_orgs
                or ":" in n.split("|")[1]}
    save_json(ARCHIVE_FILE, archive)
    save_json(NOTIFIED_FILE, sorted(notified))

    all_prs.sort(key=lambda p: p["created"] or "", reverse=True)
    with lock:
        state.update(prs=all_prs, errors=errors, lastPoll=now_iso(), me=me,
                     pollMs=int((time.monotonic() - started) * 1000))


def poll_deploys():
    rules_cfg = get_rules()
    settings = rules_cfg["settings"]
    notified = set(load_json(NOTIFIED_FILE, []))
    all_items, all_rel, errors, ok_orgs = [], [], {}, set()
    pr_ok_cache = {}
    for org in list(ORGS.values()):
        try:
            items, rels = org.fetch_deploys()
            ok_orgs.add(org.name)
        except Exception as e:  # noqa: BLE001
            errors[org.name] = str(e)
            with lock:
                all_items.extend(d for d in state["deploys"] if d["org"] == org.name)
                all_rel.extend(r for r in state["releases"] if r["org"] == org.name)
            continue
        for it in items:
            rule = matching_deploy_rule(it, rules_cfg)
            it["ruleId"] = rule["id"] if rule else None
            it["ruleName"] = (rule["name"] or "regra de deploy") if rule else None
            it["waiting"] = None
            if rule and rule["action"] == "approve":
                if settings["paused"]:
                    it["waiting"] = "pausado"
                elif rule["requirePrApproved"]:
                    pk = (org.name, it.get("prNumber"))
                    if not it.get("prNumber"):
                        it["waiting"] = "PR de origem não identificada"
                    else:
                        if pk not in pr_ok_cache:
                            try:
                                pr_ok_cache[pk] = org.pr_approved_by_me(it["prNumber"])
                            except Exception:  # noqa: BLE001
                                pr_ok_cache[pk] = False
                        if not pr_ok_cache[pk]:
                            it["waiting"] = f"sua aprovação na PR #{it['prNumber']}"
                if not it["waiting"] and time.time() - deploy_failures.get(it["key"], 0) > 600:
                    try:
                        org.decide_deploy(it, True, "Aprovado pelo PR Pilot")
                        it["done"] = True
                        log_deploy("auto", "permit" if it["kind"] == "permission" else "deploy-approve", it,
                                   detail=it["ruleName"], rule_id=rule["id"])
                        if settings["notifyAuto"]:
                            notify("PR Pilot — " + ("permissão liberada" if it["kind"] == "permission" else "release aprovada"),
                                   f"{it['org']} · {it['pipeline']}", f"{it.get('stage') or ''} {it.get('version') or ''}".strip())
                        continue
                    except Exception as e:  # noqa: BLE001
                        deploy_failures[it["key"]] = time.time()
                        errors[org.name] = f"Falha ao liberar {it['pipeline']}: {e}"
            nkey = it["key"]
            if nkey not in notified and settings["notifyDeploys"] and (it["mine"] or (rule and rule["action"] == "notify")):
                notified.add(nkey)
                what = {"release": "release aguardando aprovação", "approval": "pipeline aguardando aprovação",
                        "permission": "pipeline pedindo permissão"}[it["kind"]]
                notify(f"PR Pilot — {what}", f"{it['org']} · {it['pipeline']}",
                       ", ".join(x["name"] for x in it["resources"]) or f"{it.get('stage') or ''} · {it.get('branch') or ''}")
            all_items.append(it)
        all_rel.extend(rels)
    live = {d["key"] for d in all_items}
    notified = {n for n in notified if ":" not in n.split("|")[1] or n in live or n.split("|")[0] not in ok_orgs}
    save_json(NOTIFIED_FILE, sorted(notified))
    all_items.sort(key=lambda d: d.get("created") or "", reverse=True)
    all_rel.sort(key=lambda r: r.get("created") or "", reverse=True)
    with lock:
        state.update(deploys=all_items, releases=all_rel, deployErrors=errors, lastDeployPoll=now_iso())


def poll_loop():
    while True:
        for fn in (poll_once, poll_deploys):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                with lock:
                    state["errors"]["_geral"] = f"{fn.__name__}: {e}"
        wake.wait(max(15, int(CONFIG.get("pollSeconds", 60))))
        wake.clear()


# ---------------------------------------------------------------- análise

def hours_between(a, b):
    a, b = parse_dt(a), parse_dt(b)
    return (b - a).total_seconds() / 3600 if a and b else None


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def completed_prs(days, force=False):
    out, errors = [], {}
    for org in ORGS.values():
        c = analytics_cache.get(org.name)
        if force or not c or c["days"] < days or time.time() - c["at"] > 900:
            try:
                c = {"at": time.time(), "days": max(days, 90), "prs": org.fetch_completed(max(days, 90))}
                analytics_cache[org.name] = c
            except Exception as e:  # noqa: BLE001
                errors[org.name] = str(e)
                if not c:
                    continue
        since = now() - timedelta(days=days)
        out.extend(p for p in c["prs"] if parse_dt(p["closed"]) >= since)
    return out, errors


def analytics(days, org_filter=None, force=False):
    done, errors = completed_prs(days, force)
    with lock:
        open_prs = list(state["prs"])
    if org_filter:
        done = [p for p in done if p["org"] == org_filter]
        open_prs = [p for p in open_prs if p["org"] == org_filter]
    since = now() - timedelta(days=days)
    activity = [a for a in read_activity() if parse_dt(a["ts"]) >= since and (not org_filter or a["org"] == org_filter)]
    votes = [a for a in activity if a["action"] == "vote" and a.get("vote") in (10, 5)]

    by_creator = {}
    for p in done:
        c = by_creator.setdefault(p["creatorName"], {"name": p["creatorName"], "id": p["creatorId"], "merged": 0, "lead": [], "open": 0, "toMaster": 0})
        c["merged"] += 1
        c["lead"].append(hours_between(p["created"], p["closed"]))
        if p["target"].lower() in ("master", "main"):
            c["toMaster"] += 1
    for p in open_prs:
        by_creator.setdefault(p["creatorName"], {"name": p["creatorName"], "merged": 0, "lead": [], "open": 0, "toMaster": 0})["open"] += 1
    my_names = {o.me["name"].lower() for o in ORGS.values() if o.me} | {o.me["id"] for o in ORGS.values() if o.me}
    creators = sorted(({k: v for k, v in c.items() if k != "lead"} | {"medianLeadH": median(c["lead"])}
                       for c in by_creator.values() if c["name"].lower() not in my_names and c.get("id") not in my_names),
                      key=lambda c: (-c["merged"], -c["open"]))

    def count_by(items, key, top=12):
        d = {}
        for i in items:
            d[key(i)] = d.get(key(i), 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:top]]

    daily = {}
    for i in range(days):
        daily[(now() - timedelta(days=days - 1 - i)).date().isoformat()] = {"auto": 0, "manual": 0, "merged": 0}
    for a in votes:
        d = parse_dt(a["ts"]).astimezone().date().isoformat()
        if d in daily:
            daily[d]["auto" if a["by"] == "auto" else "manual"] += 1
    for p in done:
        d = parse_dt(p["closed"]).astimezone().date().isoformat()
        if d in daily:
            daily[d]["merged"] += 1

    ages = [hours_between(p["created"], now_iso()) for p in open_prs]
    buckets = [("< 1 dia", 0, 24), ("1–3 dias", 24, 72), ("3–7 dias", 72, 168), ("> 7 dias", 168, 10**9)]
    aging = [{"name": n, "count": sum(1 for h in ages if h is not None and lo <= h < hi)} for n, lo, hi in buckets]

    my_response = median(hours_between(a["created"], a["ts"]) for a in votes if a["by"] == "manual" and a.get("created"))
    pending = [p for p in open_prs if p["myVote"] == 0 and not p.get("archived")]
    oldest = min((p["created"] for p in pending), default=None)
    return {
        "days": days,
        "errors": errors,
        "kpis": {
            "merged": len(done),
            "medianLeadH": median(hours_between(p["created"], p["closed"]) for p in done),
            "open": len(open_prs),
            "pending": len(pending),
            "oldestPendingH": round(hours_between(oldest, now_iso()), 1) if oldest else None,
            "autoApprovals": sum(1 for a in votes if a["by"] == "auto"),
            "manualApprovals": sum(1 for a in votes if a["by"] == "manual"),
            "myMedianResponseH": my_response,
            "conflicts": sum(1 for p in open_prs if p.get("mergeStatus") == "conflicts"),
            "buildFailed": sum(1 for p in open_prs if p.get("build") == "failed"),
        },
        "creators": creators,
        "repos": count_by(done, lambda p: f"{p['org']}/{p['repo']}"),
        "targets": count_by(done, lambda p: p["target"], 8),
        "daily": [{"date": k, **v} for k, v in daily.items()],
        "aging": aging,
    }


def simulate_rule(body):
    """Testa UMA regra (em edição) contra as PRs abertas e as concluídas nos últimos 30 dias."""
    saved = get_rules()
    rule = normalize_rule(body.get("rule") or {})
    rule["enabled"] = True
    protected = protected_set({"protectedTargets": body.get("protectedTargets", saved["protectedTargets"])})
    # Precedência: a regra em edição entra na posição dela; as outras salvas continuam valendo.
    others = [r for r in saved["rules"] if r["id"] != rule["id"]]
    pos = next((i for i, r in enumerate(saved["rules"]) if r["id"] == rule["id"]), len(others))
    ordered = others[:pos] + [rule] + others[pos:]

    def describe(p):
        return {k: p.get(k) for k in ("org", "prId", "title", "creatorName", "target", "repo", "url")}

    with lock:
        open_prs = list(state["prs"])
    now_list = []
    for p in open_prs:
        if not rule_matches(rule, p, protected):
            continue
        first = next(r for r in ordered if r["enabled"] and rule_matches(r, p, protected))
        now_list.append({**describe(p), "myVote": p.get("myVote"),
                         "shadowedBy": None if first["id"] == rule["id"] else (first["name"] or f"regra {ordered.index(first) + 1}")})
    hist, errors = completed_prs(30)
    hist_matches = [p for p in hist if rule_matches(rule, p, protected)]
    by_target = {}
    for p in hist_matches:
        by_target[p["target"]] = by_target.get(p["target"], 0) + 1
    return {
        "open": now_list,
        "openTotal": len(open_prs),
        "history": {"count": len(hist_matches), "total": len(hist), "byTarget": by_target,
                    "sample": [describe(p) for p in sorted(hist_matches, key=lambda p: p["closed"] or "", reverse=True)[:6]]},
        "errors": errors,
    }


def simulate_deploy_rule(body):
    rule = normalize_deploy_rule(body.get("rule") or {})
    rule["enabled"] = True
    saved = [r for r in get_rules()["deployRules"] if r["enabled"]]
    pos = next((i for i, r in enumerate(saved) if r["id"] == rule["id"]), len(saved))
    ordered = [r for r in saved if r["id"] != rule["id"]]
    ordered = ordered[:pos] + [rule] + ordered[pos:]
    with lock:
        items, rels = list(state["deploys"]), list(state["releases"])
    now_list = []
    for it in items:
        if deploy_rule_matches(rule, it):
            first = next(r for r in ordered if deploy_rule_matches(r, it))
            now_list.append({k: it.get(k) for k in ("kind", "org", "title", "pipeline", "stage", "branch", "version", "prNumber", "resources")}
                            | {"shadowedBy": None if first["id"] == rule["id"] else (first["name"] or "outra regra")})
    hist = []
    if rule["kind"] == "release":
        # Cada estágio de cada release recente vira um "teria agido" se casar com a regra.
        for r in rels:
            for e in r["envs"]:
                fake = {"kind": "release", "org": r["org"], "pipeline": r["pipeline"], "stage": e["name"], "branch": r["branch"], "resources": []}
                if e["status"] != "notStarted" and deploy_rule_matches(rule, fake):
                    hist.append({"org": r["org"], "pipeline": r["pipeline"], "stage": e["name"], "branch": r["branch"],
                                 "version": r["version"], "created": r["created"], "status": e["status"]})
    return {"open": now_list, "openTotal": len(items), "history": hist[:50], "historyCount": len(hist),
            "historyTotal": sum(len(r["envs"]) for r in rels)}


def public_config():
    cfg = load_json(CONFIG_FILE, {})
    return {
        "pollSeconds": cfg.get("pollSeconds", 60),
        "port": cfg.get("port", DEFAULT_PORT),
        "dataDir": DATA,
        "orgs": [{"name": o["name"], "url": o["url"], "enabled": o.get("enabled", True),
                  "hasPat": bool(o.get("pat") or o.get("patCommand")), "patCommand": bool(o.get("patCommand")),
                  "me": (ORGS[o["name"]].me if o["name"] in ORGS else None)} for o in cfg.get("orgs", [])],
    }


def normalize_org_url(url):
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "https://dev.azure.com/" + url  # aceita só o nome da organização
    return url


def test_org(body):
    """Testa uma organização (nova ou salva) sem gravar nada. PAT vazio = usa o já salvo."""
    url = normalize_org_url(body.get("url"))
    cfg = {"name": body.get("name") or "teste", "url": url, "pat": (body.get("pat") or "").strip()}
    if not cfg["pat"]:
        saved = next((o for o in load_json(CONFIG_FILE, {}).get("orgs", []) if o["name"] == body.get("originalName")), None)
        if not saved:
            raise ValueError("Informe o PAT")
        cfg = {**saved, "url": url, "name": cfg["name"]}
    org = Org(cfg)
    checks = []

    def check(label, fn):
        try:
            checks.append({"label": label, "ok": True, "detail": fn()})
            return True
        except Exception as e:  # noqa: BLE001
            checks.append({"label": label, "ok": False, "detail": str(e)[:240]})
            return False

    if not check("Conectar e identificar a conta", lambda: (lambda m: f"{m['name']} · {m['email']}")(org.identity())):
        return {"ok": False, "checks": checks}
    projects = []
    check("Listar projetos", lambda: (projects.extend(org.projects()), ", ".join(p["name"] for p in projects[:6]) or "nenhum")[1])
    proj = urllib.parse.quote(projects[0]["name"]) if projects else None
    if proj:
        check("Ler pull requests (Code)", lambda: f"{len(org.req('GET', f'{proj}/_apis/git/pullrequests?$top=50&{API}')['value'])} abertas no 1º projeto")
        check("Ler builds (Build)", lambda: f"{len(org.req('GET', f'{proj}/_apis/build/builds?$top=5&{API}')['value'])} builds recentes lidos")
        check("Ler releases (Release)", lambda: f"{len(org.req('GET', f'{org.vsrm}/{proj}/_apis/release/definitions?$top=200&{API}')['value'])} pipelines de release")
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def save_config(body):
    current = load_json(CONFIG_FILE, {})
    old = {o["name"]: o for o in current.get("orgs", [])}
    orgs, names = [], set()
    for o in body.get("orgs", []):
        name, url = (o.get("name") or "").strip(), normalize_org_url(o.get("url"))
        if not name or not url.startswith("https://"):
            raise ValueError("Cada organização precisa de nome e URL https://")
        if name.lower() in names:
            raise ValueError(f"Nome repetido: {name}")
        names.add(name.lower())
        prev = old.get(o.get("originalName") or name, {})
        entry = {"name": name, "url": url, "enabled": bool(o.get("enabled", True))}
        pat = (o.get("pat") or "").strip()
        if pat:
            entry["pat"] = pat
        elif prev.get("pat"):
            entry["pat"] = prev["pat"]
        elif prev.get("patCommand"):
            entry["patCommand"] = prev["patCommand"]
        else:
            raise ValueError(f"{name}: informe o PAT")
        orgs.append(entry)
    cfg = {**current, "orgs": orgs, "pollSeconds": min(max(int(body.get("pollSeconds") or 60), 15), 3600)}
    save_json(CONFIG_FILE, cfg)
    os.chmod(CONFIG_FILE, 0o600)
    reload_orgs()


def rule_stats():
    since = now() - timedelta(days=30)
    stats = {}
    for a in read_activity():
        rid = a.get("ruleId")
        if not rid or a["by"] != "auto" or parse_dt(a["ts"]) < since:
            continue
        st = stats.setdefault(rid, {"count": 0, "last": None})
        st["count"] += 1
        st["last"] = max(st["last"] or "", a["ts"])
    return stats


# ---------------------------------------------------------------- HTTP

def find_pr(org, pr_id):
    with lock:
        return next((p for p in state["prs"] if p["org"] == org and p["prId"] == int(pr_id)), None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            with open(UI_FILE, "rb") as f:
                return self.send(200, f.read(), "text/html")
        if url.path == "/api/state":
            with lock:
                payload = {k: state[k] for k in ("prs", "errors", "lastPoll", "me", "pollMs")}
            payload["orgs"] = list(ORGS.keys())
            payload["pollSeconds"] = CONFIG.get("pollSeconds", 60)
            payload["rules"] = get_rules()
            payload["archive"] = load_json(ARCHIVE_FILE, {})
            payload["activity"] = read_activity(300)
            seen = {}
            for p in payload["prs"]:
                seen.setdefault(p["creatorUnique"] or p["creatorName"], p["creatorName"])
            for a in payload["activity"]:
                seen.setdefault(a.get("creatorName"), a.get("creatorName"))
            hist = [p for c in list(analytics_cache.values()) for p in c["prs"]]
            my_ids = {o.me["id"] for o in ORGS.values() if o.me}
            for p in hist:
                if p["creatorId"] not in my_ids:
                    seen.setdefault(p["creatorUnique"] or p["creatorName"], p["creatorName"])
            payload["creators"] = sorted({v for v in seen.values() if v}, key=str.lower)
            payload["repos"] = sorted({p["repo"] for p in payload["prs"] + hist}, key=str.lower)
            counts = {}
            for p in payload["prs"] + hist:
                counts[p["target"]] = counts.get(p["target"], 0) + 1
            payload["targets"] = [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:12]
            payload["ruleStats"] = rule_stats()
            with lock:
                payload["deploys"] = list(state["deploys"])
                payload["releases"] = list(state["releases"])
                payload["deployErrors"] = dict(state["deployErrors"])
                payload["lastDeployPoll"] = state["lastDeployPoll"]
            payload["configured"] = bool(ORGS)
            return self.send(200, payload)
        if url.path == "/api/config":
            return self.send(200, public_config())
        if url.path == "/api/summary":  # leve: usado pelo app para o contador no Dock e na barra de menus
            with lock:
                prs = sum(1 for p in state["prs"] if not p.get("archived") and p["myVote"] == 0)
                deploys = len(state["deploys"])
                errors = bool(state["errors"] or state["deployErrors"])
            return self.send(200, {"prs": prs, "deploys": deploys, "total": prs + deploys, "errors": errors,
                                   "configured": bool(ORGS), "lastPoll": state["lastPoll"]})
        if url.path == "/api/analytics":
            try:
                days = min(max(int((qs.get("days") or ["30"])[0]), 1), 90)
                return self.send(200, analytics(days, (qs.get("org") or [None])[0] or None,
                                                force=(qs.get("force") or ["0"])[0] == "1"))
            except Exception as e:  # noqa: BLE001
                return self.send(500, {"error": str(e)})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        # Header custom força preflight CORS (que não respondemos): outro site não consegue agir por você.
        if self.headers.get("X-PR-Pilot") != "1":
            return self.send(403, {"error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            if self.path == "/api/vote":
                vote = int(body["vote"])
                if vote not in (10, 5, 0, -5, -10):
                    raise ValueError("voto inválido")
                pr = find_pr(body["org"], body["prId"])
                if not pr:
                    raise ValueError("PR não está mais na lista — atualize")
                ORGS[pr["org"]].vote(pr["project"], pr["repoId"], pr["prId"], vote)
                with lock:
                    pr["myVote"] = vote
                log_activity("manual", "vote", pr, vote=vote)
                return self.send(200, {"ok": True})
            if self.path == "/api/archive":
                archive = load_json(ARCHIVE_FILE, {})
                for item in body.get("items", []):
                    key = pr_key(item["org"], item["prId"])
                    pr = find_pr(item["org"], item["prId"])
                    if body.get("archive", True):
                        if pr:
                            archive[key] = {"ts": now_iso(), "commit": pr["commit"], "reason": "manual", **pr_summary(pr)}
                            pr["archived"] = True
                            log_activity("manual", "archive", pr)
                    elif key in archive:
                        info = archive.pop(key)
                        if pr:
                            pr["archived"] = False
                        log_activity("manual", "unarchive", pr or info)
                save_json(ARCHIVE_FILE, archive)
                return self.send(200, {"ok": True})
            if self.path == "/api/rules":
                save_json(RULES_FILE, clean_rules(body))
                wake.set()
                return self.send(200, {"ok": True})
            if self.path == "/api/simulate":
                return self.send(200, simulate_rule(body))
            if self.path == "/api/simulate-deploy":
                return self.send(200, simulate_deploy_rule(body))
            if self.path == "/api/deploy":
                with lock:
                    item = next((d for d in state["deploys"] if d["key"] == body.get("key")), None)
                if not item:
                    raise ValueError("Item não está mais pendente — atualize")
                approve = body.get("decision") == "approve"
                ORGS[item["org"]].decide_deploy(item, approve, (body.get("comment") or "").strip())
                with lock:
                    state["deploys"] = [d for d in state["deploys"] if d["key"] != item["key"]]
                action = {("permission", True): "permit", ("permission", False): "cancel"}.get(
                    (item["kind"], approve), "deploy-approve" if approve else "deploy-reject")
                log_deploy("manual", action, item, detail=body.get("comment") or None)
                wake.set()
                return self.send(200, {"ok": True})
            if self.path == "/api/config/test":
                return self.send(200, test_org(body))
            if self.path == "/api/config":
                save_config(body)
                return self.send(200, {"ok": True})
            if self.path == "/api/refresh":
                wake.set()
                return self.send(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})


def main():
    if not os.path.exists(RULES_FILE):
        save_json(RULES_FILE, DEFAULT_RULES)
    port = int(os.environ.get("PR_PILOT_PORT") or CONFIG.get("port") or DEFAULT_PORT)
    url = f"http://127.0.0.1:{port}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"Porta {port} em uso — o PR Pilot provavelmente já está rodando (serviço do install.sh?). Abra {url}", flush=True)
        if os.environ.get("PR_PILOT_OPEN") == "1":
            webbrowser.open(url)
        raise SystemExit(1)
    threading.Thread(target=poll_loop, daemon=True).start()
    print(f"PR Pilot em {url} — orgs: {', '.join(ORGS) or '(nenhuma — configure na tela Ambiente)'} — dados em {DATA}", flush=True)
    if os.environ.get("PR_PILOT_OPEN") == "1":
        webbrowser.open(url + ("" if ORGS else "/#ambiente"))
    server.serve_forever()


if __name__ == "__main__":
    main()
