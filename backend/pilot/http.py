"""HTTP local (127.0.0.1): a tela (ui/ compilada em static/) e a API que ela usa.

Toda rota /api exige a chave da execução (X-Commitdeck-Token) e os POSTs exigem também o header X-Commitdeck: 1 —
header custom força preflight de CORS, que não respondemos, então nenhum site consegue agir por você.
"""
import ctypes
import hmac
import json
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import accounts, analytics, azure, catalogs, engine, git, github, library, rules, update
from .core import (APP_BUILD, APP_PLATFORM, APP_VERSION, ARCHIVE_FILE, CONFIG_FILE, DATA, DEFAULT_PORT, PRODUCT, RULES_FILE,
                   STATIC_DIR, TOKEN, ctx, load_json, lock, log_activity, log_build, log_deploy, notifications, notify_seq,
                   now_iso, pr_summary, read_activity, save_json, state, wake)

GET, POST = {}, {}


def route(method, path):
    def deco(fn):
        (GET if method == "GET" else POST)[path] = fn
        return fn
    return deco


def q1(qs, name, default=None):
    return (qs.get(name) or [default])[0]


def find_item(kind, key):
    with lock:
        pool = {"pr": state["prs"] + state["myPrs"], "deploy": state["deploys"], "build": state["builds"]}[kind]
        return next((x for x in pool if x["key"] == key), None)


# ---------------------------------------------------------------- estado geral
@route("GET", "/api/state")
def get_state(qs, body):
    with lock:
        payload = {k: state[k] for k in ("prs", "myPrs", "builds", "buildErrors", "errors", "lastPoll", "me", "pollMs",
                                         "deploys", "releases", "deployErrors", "lastDeployPoll", "lastBuildPoll",
                                         "issues", "issueErrors", "lastIssuePoll", "polling")}
        payload = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in payload.items()}
    payload["orgs"] = list(ctx.orgs.keys())
    payload["githubAccounts"] = [{"id": a.id, "login": a.login, "avatar": (a.me or {}).get("avatar") or a.cfg.get("avatar")}
                                 for a in ctx.gh.values()]
    payload["sources"] = sorted({p["org"] for p in payload["prs"] + payload["myPrs"] + payload["builds"]} | set(ctx.orgs), key=str.lower)
    payload["pollSeconds"] = ctx.config.get("pollSeconds", 60)
    payload["editor"] = ctx.config.get("editor") or "vscode"
    payload["theme"] = ctx.config.get("theme") or "system"
    payload["rules"] = rules.get_rules()
    payload["archive"] = load_json(ARCHIVE_FILE, {})
    payload["activity"] = read_activity(300)
    seen = {}
    for p in payload["prs"]:
        seen.setdefault(p["creatorUnique"] or p["creatorName"], p["creatorName"])
    hist = [p for c in list(analytics.analytics_cache.values()) for p in c["prs"]]
    my_ids = {o.me["id"] for o in ctx.orgs.values() if o.me}
    for p in hist:
        if p["creatorId"] not in my_ids:
            seen.setdefault(p["creatorUnique"] or p["creatorName"], p["creatorName"])
    payload["creators"] = sorted({v for v in seen.values() if v}, key=str.lower)
    payload["repos"] = sorted({p["repo"] for p in payload["prs"] + hist}, key=str.lower)
    counts = {}
    for p in payload["prs"] + hist:
        counts[p["target"]] = counts.get(p["target"], 0) + 1
    payload["targets"] = [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:12]
    payload["ruleStats"] = rules.rule_stats()
    payload["configured"] = bool(ctx.orgs or ctx.gh)
    payload["app"] = {"version": APP_VERSION, "build": APP_BUILD, "platform": APP_PLATFORM, "product": PRODUCT}
    payload["update"] = dict(update.update_state)
    return payload


@route("GET", "/api/summary")
def get_summary(qs, body):
    with lock:
        prs = sum(1 for p in state["prs"] if not p.get("archived") and p["myVote"] == 0
                  and (p.get("provider") != "github" or p.get("reviewRequested")))
        deploys = sum(1 for d in state["deploys"] if d.get("mine", True))
        errors = bool(state["errors"] or state["deployErrors"])
        return {"prs": prs, "deploys": deploys, "total": prs + deploys, "errors": errors,
                "configured": bool(ctx.orgs or ctx.gh), "lastPoll": state["lastPoll"], "notifySeq": notify_seq()}


@route("GET", "/api/notifications")
def get_notifications(qs, body):
    after = int(q1(qs, "after", "0"))
    with lock:
        return {"seq": notify_seq(), "items": [n for n in notifications if n["seq"] > after]}


@route("GET", "/api/analytics")
def get_analytics(qs, body):
    days = min(max(int(q1(qs, "days", "30")), 1), 90)
    return analytics.analytics(days, q1(qs, "org") or None, force=q1(qs, "force", "0") == "1")


@route("POST", "/api/refresh")
def post_refresh(qs, body):
    wake.set()
    return {"ok": True}


# ---------------------------------------------------------------- PRs, deploys, builds
@route("POST", "/api/vote")
def post_vote(qs, body):
    vote = int(body["vote"])
    if vote not in (10, 5, 0, -5, -10):
        raise ValueError("voto inválido")
    pr = find_item("pr", body.get("key"))
    if not pr:
        raise ValueError("PR não está mais na lista — atualize")
    engine.vote_pr(engine.account_for_item(pr), pr, vote, (body.get("comment") or "").strip())
    with lock:
        pr["myVote"] = vote
    log_activity("manual", "vote", pr, vote=vote)
    return {"ok": True}


@route("POST", "/api/archive")
def post_archive(qs, body):
    archive = load_json(ARCHIVE_FILE, {})
    for key in body.get("keys", []):
        pr = find_item("pr", key)
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
    return {"ok": True}


@route("POST", "/api/deploy")
def post_deploy(qs, body):
    item = find_item("deploy", body.get("key"))
    if not item:
        raise ValueError("Item não está mais pendente — atualize")
    approve = body.get("decision") == "approve"
    engine.account_for_item(item).decide_deploy(item, approve, (body.get("comment") or "").strip())
    with lock:
        state["deploys"] = [d for d in state["deploys"] if d["key"] != item["key"]]
    action = {("permission", True): "permit", ("permission", False): "cancel"}.get((item["kind"], approve),
                                                                                  "deploy-approve" if approve else "deploy-reject")
    log_deploy("manual", action, item, detail=body.get("comment") or None)
    wake.set()
    return {"ok": True}


@route("GET", "/api/build")
def get_build(qs, body):
    b = find_item("build", q1(qs, "key", ""))
    if not b:
        raise LookupError("build não está mais na lista")
    acc = engine.account_for_item(b)
    return acc.run_detail(b["project"], b["id"]) if b.get("provider") == "github" else acc.build_detail(b["project"], b["id"])


@route("POST", "/api/build-action")
def post_build_action(qs, body):
    b = find_item("build", body.get("key"))
    if not b:
        raise ValueError("Build não está mais na lista — atualize")
    acc = engine.account_for_item(b)
    (acc.run_action if b.get("provider") == "github" else acc.build_action)(b, body.get("action"))
    log_build("manual", body.get("action"), b)
    wake.set()
    return {"ok": True}


# ---------------------------------------------------------------- regras
@route("POST", "/api/rules")
def post_rules(qs, body):
    save_json(RULES_FILE, rules.clean_rules(body))
    wake.set()
    return {"ok": True}


@route("POST", "/api/simulate")
def post_simulate(qs, body):
    return rules.simulate_rule(body)


@route("POST", "/api/simulate-deploy")
def post_simulate_deploy(qs, body):
    return rules.simulate_deploy_rule(body)


# ---------------------------------------------------------------- contas e preferências
@route("GET", "/api/config")
def get_config(qs, body):
    return accounts.public_config()


@route("POST", "/api/config")
def post_config(qs, body):
    accounts.save_azure(body)
    return {"ok": True}


@route("POST", "/api/config/test")
def post_config_test(qs, body):
    return azure.test_org(body)


@route("POST", "/api/prefs")
def post_prefs(qs, body):
    accounts.save_prefs(body)
    return {"ok": True}


@route("POST", "/api/github/token")
def post_github_token(qs, body):
    return accounts.add_github_token(body.get("token"))


@route("POST", "/api/github/cli")
def post_github_cli(qs, body):
    return accounts.add_github_token(github.gh_cli_token(), source="gh-cli")


@route("POST", "/api/github/device/start")
def post_github_device(qs, body):
    return github.device_start(lambda tok: accounts.add_github_token(tok, source="device"))


@route("GET", "/api/github/device")
def get_github_device(qs, body):
    f = github.device_flows.get(q1(qs, "id", ""))
    if not f:
        raise LookupError("login não encontrado")
    return {k: f[k] for k in ("id", "status", "userCode", "verificationUri", "error", "account")}


@route("POST", "/api/github/remove")
def post_github_remove(qs, body):
    accounts.remove_github(body.get("id"))
    return {"ok": True}


@route("POST", "/api/github/test")
def post_github_test(qs, body):
    return accounts.test_github(body)


# ---------------------------------------------------------------- atualização do app
@route("POST", "/api/update/check")
def post_update_check(qs, body):
    return update.check_update()


@route("POST", "/api/update/download")
def post_update_download(qs, body):
    return update.download_update()


# ---------------------------------------------------------------- repositórios locais
@route("GET", "/api/repos")
def get_repos(qs, body):
    return {"repos": git.list_repos(with_status=q1(qs, "status", "1") == "1")}


@route("POST", "/api/repos/add")
def post_repos_add(qs, body):
    return git.add_repo(body.get("path") or "")


@route("POST", "/api/repos/scan")
def post_repos_scan(qs, body):
    return git.scan(body.get("path") or "", int(body.get("depth") or 3))


@route("POST", "/api/repos/clone")
def post_repos_clone(qs, body):
    url = (body.get("url") or "").strip()
    info = git.parse_remote(url)
    auth = engine.git_auth(info.get("provider"), info.get("owner")) if url.startswith("https://") else None
    return git.clone(url, body.get("dest") or "", auth=auth)


@route("POST", "/api/repos/remove")
def post_repos_remove(qs, body):
    git.remove_repo(body.get("id"))
    return {"ok": True}


@route("POST", "/api/repos/pin")
def post_repos_pin(qs, body):
    git.set_pinned(body.get("id"), body.get("pinned"))
    return {"ok": True}


@route("GET", "/api/repo/status")
def get_repo_status(qs, body):
    return git.status(q1(qs, "id"))


@route("GET", "/api/repo/graph")
def get_repo_graph(qs, body):
    return git.graph(q1(qs, "id"), int(q1(qs, "limit", "400")), q1(qs, "ref") or None, q1(qs, "all", "1") == "1",
                     q1(qs, "author") or None, q1(qs, "search") or None, int(q1(qs, "skip", "0")))


@route("GET", "/api/repo/commit")
def get_repo_commit(qs, body):
    return git.commit_detail(q1(qs, "id"), q1(qs, "sha", ""))


@route("GET", "/api/repo/diff")
def get_repo_diff(qs, body):
    return git.diff(q1(qs, "id"), q1(qs, "path") or None, q1(qs, "sha") or None, q1(qs, "staged", "0") == "1",
                    int(q1(qs, "context", "3")))


@route("GET", "/api/repo/refs")
def get_repo_refs(qs, body):
    return git.refs(q1(qs, "id"))


@route("GET", "/api/repo/clean-check")
def get_repo_clean_check(qs, body):
    return {"blockers": git.clean_blockers(q1(qs, "id"))}


REPO_ACTIONS = {
    "stage": lambda b: git.stage(b["id"], b.get("paths")),
    "stage-all": lambda b: git.stage_all(b["id"]),
    "unstage": lambda b: git.unstage(b["id"], b.get("paths")),
    "discard": lambda b: git.discard(b["id"], b.get("paths")),
    "commit": lambda b: git.commit(b["id"], b.get("message"), bool(b.get("amend")), bool(b.get("stageAll"))),
    "checkout": lambda b: git.checkout(b["id"], b.get("ref"), track=b.get("track")),
    "branch-create": lambda b: git.create_branch(b["id"], b.get("name"), b.get("start"), b.get("switch", True)),
    "branch-delete": lambda b: git.delete_branch(b["id"], b.get("name"), bool(b.get("force")), bool(b.get("remote"))),
    "branch-rename": lambda b: git.rename_branch(b["id"], b.get("old"), b.get("new")),
    "fetch": lambda b: git.fetch(b["id"]),
    "pull": lambda b: git.pull(b["id"], bool(b.get("rebase"))),
    "push": lambda b: git.push(b["id"], bool(b.get("force"))),
    "merge": lambda b: git.merge(b["id"], b.get("ref")),
    "cherry-pick": lambda b: git.cherry_pick(b["id"], b.get("sha")),
    "revert": lambda b: git.revert(b["id"], b.get("sha")),
    "stash": lambda b: git.stash(b["id"], b.get("action"), b.get("ref"), b.get("message")),
    "tag": lambda b: git.create_tag(b["id"], b.get("name"), b.get("sha"), b.get("message")),
    "reset": lambda b: git.reset(b["id"], b.get("sha"), b.get("mode", "mixed")),
    "abort": lambda b: git.abort_operation(b["id"]),
    "continue": lambda b: git.continue_operation(b["id"]),
    "clean": lambda b: git.clean_local(b["id"]),
}
for _name, _fn in REPO_ACTIONS.items():
    POST[f"/api/repo/{_name}"] = (lambda fn: lambda qs, body: fn(body) or {"ok": True})(_fn)


@route("POST", "/api/open")
def post_open(qs, body):
    path = git.get_repo(body["id"])["path"] if body.get("id") else body.get("path")
    git.open_in(path, body.get("target"), body.get("editor") or ctx.config.get("editor") or "vscode", body.get("file"))
    return {"ok": True}


@route("GET", "/api/jobs")
def get_job(qs, body):
    job = git.jobs.get(q1(qs, "id", ""))
    if not job:
        raise LookupError("tarefa não encontrada")
    return job


@route("POST", "/api/pr/create")
def post_pr_create(qs, body):
    repo = git.get_repo(body["repoId"])
    info = git.parse_remote(repo.get("remoteUrl"))
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("Dê um título para a PR")
    source, target = body.get("source"), body.get("target")
    if not source or not target or source == target:
        raise ValueError("Escolha a branch de origem e a de destino (diferentes)")
    if info.get("provider") == "github":
        acc = engine.gh_by_login(info["owner"]) or next(iter(ctx.gh.values()), None)
        if not acc:
            raise ValueError("Conecte uma conta do GitHub para criar PRs neste repositório")
        res = acc.create_pr(info["slug"], source, target, title, body.get("description") or "", body.get("draft"))
    elif info.get("provider") == "azure":
        org = next((o for o in ctx.orgs.values() if o.url.rstrip("/").rsplit("/", 1)[-1].lower() == info["owner"].lower()
                    or o.name.lower() == info["owner"].lower()), None)
        if not org:
            raise ValueError(f"A organização {info['owner']} do Azure não está conectada")
        res = org.create_pr(info["project"], info["name"], source, target, title, body.get("description") or "", body.get("draft"))
    else:
        raise ValueError("O remoto deste repositório não é do GitHub nem do Azure DevOps")
    log_activity("manual", "pr-create", {"key": None, "provider": info["provider"], "org": info["owner"], "prId": res["id"],
                                         "title": title, "target": target, "repo": info["name"], "url": res["url"]})
    wake.set()
    return res


# ---------------------------------------------------------------- catálogos
# ---------------------------------------------------------------- favoritos e tags (qualquer conta)
@route("GET", "/api/library")
def get_library(qs, body):
    return library.view()


@route("GET", "/api/library/search")
def get_library_search(qs, body):
    return library.search(q1(qs, "q", ""), force=q1(qs, "force", "0") == "1")


@route("POST", "/api/library/favorite")
def post_library_favorite(qs, body):
    return library.favorite(body)


@route("POST", "/api/library/tags")
def post_library_tags(qs, body):
    return library.set_tags(body)


@route("POST", "/api/library/tag")
def post_library_tag(qs, body):
    return library.save_tag(body)


@route("POST", "/api/library/tag/delete")
def post_library_tag_delete(qs, body):
    library.delete_tag(body.get("name"))
    return {"ok": True}


@route("POST", "/api/library/clone")
def post_library_clone(qs, body):
    return library.clone(body.get("key"), body.get("dest"))


@route("GET", "/api/catalogs")
def get_catalogs(qs, body):
    return {"catalogs": catalogs.load()}


@route("GET", "/api/catalog")
def get_catalog(qs, body):
    return catalogs.view(q1(qs, "id"), force=q1(qs, "force", "0") == "1")


@route("GET", "/api/catalogs/suggestions")
def get_catalog_suggestions(qs, body):
    return {"suggestions": catalogs.suggestions()}


@route("POST", "/api/catalogs/save")
def post_catalog_save(qs, body):
    return catalogs.upsert(body)


@route("POST", "/api/catalogs/delete")
def post_catalog_delete(qs, body):
    catalogs.delete(body.get("id"))
    return {"ok": True}


@route("POST", "/api/catalogs/clone")
def post_catalog_clone(qs, body):
    return catalogs.clone(body.get("id"), body.get("repoKey"), body.get("dest") or None)


@route("GET", "/api/remote-repos")
def get_remote_repos(qs, body):
    src = {"provider": q1(qs, "provider"), "account": q1(qs, "account", ""), "owner": q1(qs, "owner"), "project": q1(qs, "project")}
    return {"repos": catalogs.remote_repos(src, force=q1(qs, "force", "0") == "1")}


# ---------------------------------------------------------------- servidor
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json", cache=False):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/json", "application/javascript")) else ""))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return not TOKEN or hmac.compare_digest(self.headers.get("X-Commitdeck-Token") or "", TOKEN)

    def static(self, path):
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            full = os.path.join(STATIC_DIR, "index.html")   # app de página única
        if not os.path.isfile(full):
            return self.send(503, b"<h1>Tela n\xc3\xa3o compilada</h1><p>Rode: cd ui && npm install && npm run build</p>", "text/html")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".js"):
            ctype = "application/javascript"
        with open(full, "rb") as f:
            return self.send(200, f.read(), ctype, cache="/assets/" in full.replace(os.sep, "/"))

    def dispatch(self, table, body):
        url = urllib.parse.urlparse(self.path)
        fn = table.get(url.path)
        if not fn:
            return self.send(404, {"error": "rota não encontrada"})
        try:
            return self.send(200, fn(urllib.parse.parse_qs(url.query), body))
        except LookupError as e:
            return self.send(404, {"error": str(e).strip("'")})
        except (ValueError, git.GitError) as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self.send(500, {"error": str(e)[:600]})

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith("/api/"):
            return self.static(path)
        if not self.authorized():
            return self.send(401, {"error": "abra pelo app"})
        return self.dispatch(GET, None)

    def do_POST(self):
        if self.headers.get("X-Commitdeck") != "1" or not self.authorized():
            return self.send(403, {"error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send(400, {"error": "JSON inválido"})
        return self.dispatch(POST, body)


def _watch_parent(parent):
    def alive(pid):
        if os.name != "nt":
            return os.getppid() == pid
        k32 = ctypes.windll.kernel32  # no Windows o getppid não muda quando o pai morre
        h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) != 0  # 0 = sinalizado = processo terminou
        finally:
            k32.CloseHandle(h)
    while True:
        time.sleep(3)
        if not alive(int(parent)):
            os._exit(0)  # o app fechou (ou caiu): não fica processo órfão segurando a porta


def main():
    if not os.path.exists(RULES_FILE):
        save_json(RULES_FILE, rules.DEFAULT_RULES)
    port = int(os.environ.get("COMMITDECK_PORT") or load_json(CONFIG_FILE, {}).get("port") or DEFAULT_PORT)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"Porta {port} em uso — já há um {PRODUCT} rodando.", flush=True)
        raise SystemExit(1)
    server.daemon_threads = True
    if os.environ.get("COMMITDECK_PARENT_PID"):
        threading.Thread(target=_watch_parent, args=(os.environ["COMMITDECK_PARENT_PID"],), daemon=True).start()
    engine.start()
    threading.Thread(target=update.update_loop, daemon=True).start()
    print(f"{PRODUCT} {APP_VERSION} ({APP_BUILD}, {APP_PLATFORM}) em http://127.0.0.1:{port} — Azure: {', '.join(ctx.orgs) or '-'}"
          f" — GitHub: {', '.join(a.login for a in ctx.gh.values()) or '-'} — dados em {DATA}{' — token ativo' if TOKEN else ''}", flush=True)
    server.serve_forever()
