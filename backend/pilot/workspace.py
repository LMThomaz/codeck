"""Projetos abertos no app (abas), tarefas em worktree e acesso aos arquivos do projeto.

Projeto = um repositório local registrado (git.add_repo), aberto como aba. Cada projeto tem:
  · tarefas: uma branch + um worktree próprio + os terminais/agentes dela. Assim várias tarefas (e vários agentes)
    andam em paralelo sem stash nem troca de branch;
  · ajustes: arquivos que o Git não leva e que o worktree precisa (workspace.local.json, nuget.config, .env…),
    o script de preparação e onde ficam os worktrees.

workspace.json: {"open": [repoId…], "active": repoId, "projects": {repoId: {settings, tasks: [...]}}}
Os worktrees ficam em <pasta-base da conta, ou a pasta-mãe do repo>/.worktrees/<repo>/<slug> — pasta oculta, que a
busca de clones ignora.
"""
import fnmatch
import os
import re
import shutil
import subprocess
import unicodedata
import uuid

from . import agents, catalogs, git, terminals
from .core import DATA, load_json, now_iso, save_json

FILE = os.path.join(DATA, "workspace.json")
DEFAULT_COPY = ["workspace.local.json", "nuget.config", "NuGet.Config", ".env", ".env.local", "appsettings.Development.json",
                "**/appsettings.Development.json", "**/appsettings.Local.json", ".claude/settings.local.json"]
MAX_FILE = 2_000_000


def _load():
    d = load_json(FILE, {})
    d.setdefault("open", [])
    d.setdefault("projects", {})
    return d


def _save(d):
    save_json(FILE, d)


def _proj(d, rid):
    p = d["projects"].setdefault(rid, {})
    p.setdefault("tasks", [])
    p.setdefault("settings", {"copy": DEFAULT_COPY, "setup": "", "worktreeRoot": ""})
    return p


# ---------------------------------------------------------------- projetos (abas)
def state():
    d = _load()
    repos = {r["id"]: r for r in git.list_repos(with_status=False)}
    out = []
    for rid in d["open"]:
        r = repos.get(rid)
        if not r:
            continue
        p = _proj(d, rid)
        live = {x["meta"].get("sid") for x in terminals.list_all(project=rid)}
        tasks = []
        for t in p["tasks"]:
            tasks.append({**t, "exists": os.path.isdir(t["path"]),
                          "terms": [x for x in terminals.list_all(task=t["id"])],
                          "resumable": agents.resumable(rid, t["id"], live)})
        out.append({"id": rid, "name": r["name"], "path": r["path"], "provider": r.get("provider"), "slug": r.get("slug"),
                    "webUrl": r.get("webUrl"), "settings": p["settings"], "tasks": tasks,
                    "terms": [x for x in terminals.list_all(project=rid) if not x["meta"].get("task")],
                    "resumable": agents.resumable(rid, None, live)})
    return {"projects": out, "active": d.get("active"), "sessions": agents.all_sessions()}


def open_project(repo_id=None, path=None):
    r = git.get_repo(repo_id) if repo_id else git.add_repo(path)
    d = _load()
    if r["id"] not in d["open"]:
        d["open"].append(r["id"])
    d["active"] = r["id"]
    _proj(d, r["id"])
    _save(d)
    return {"id": r["id"]}


def close_project(repo_id):
    d = _load()
    d["open"] = [x for x in d["open"] if x != repo_id]
    if d.get("active") == repo_id:
        d["active"] = d["open"][-1] if d["open"] else None
    _save(d)
    for t in terminals.list_all(project=repo_id):
        terminals.close(t["id"])


def activate(repo_id):
    d = _load()
    d["active"] = repo_id
    _save(d)


def reorder(ids):
    d = _load()
    d["open"] = [x for x in ids if x in d["open"]] + [x for x in d["open"] if x not in ids]
    _save(d)


def save_settings(repo_id, body):
    d = _load()
    s = _proj(d, repo_id)["settings"]
    if isinstance(body.get("copy"), list):
        s["copy"] = [str(x).strip() for x in body["copy"] if str(x).strip()][:60]
    if "setup" in body:
        s["setup"] = str(body.get("setup") or "")[:2000]
    if "worktreeRoot" in body:
        s["worktreeRoot"] = os.path.expanduser(str(body.get("worktreeRoot") or "").strip())
    if "shell" in body:
        s["shell"] = str(body.get("shell") or "").strip()[:300]
    if isinstance(body.get("addDirs"), list):
        s["addDirs"] = [os.path.abspath(os.path.expanduser(str(x))) for x in body["addDirs"] if str(x).strip()][:20]
    _save(d)
    return s


# ---------------------------------------------------------------- tarefas (branch + worktree + agentes)
def slugify(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:48].strip("-") or "tarefa"


def _worktree_root(repo, settings):
    if settings.get("worktreeRoot"):
        return settings["worktreeRoot"]
    acc = catalogs.account_dirs(f"{repo.get('provider')}:{(repo.get('slug') or '').split('/')[0]}") if repo.get("provider") else []
    parent = next((b for b in acc if os.path.normcase(repo["path"]).startswith(os.path.normcase(b))), None) or os.path.dirname(repo["path"])
    return os.path.join(parent, ".worktrees", repo["name"])


def _exclude_from_enclosing_repo(wt_root):
    """Se a pasta .worktrees fica dentro de OUTRO repositório (ex.: cifal/apis é o repo orquestrador), ela apareceria
    como "não versionada" nele. Põe a pasta no .git/info/exclude desse repo — local, nunca vai para commit."""
    try:
        top = git.run(os.path.dirname(wt_root), "rev-parse", "--show-toplevel").strip()
        gitdir = git.run(top, "rev-parse", "--absolute-git-dir").strip()
    except Exception:  # noqa: BLE001 — não está dentro de repositório nenhum
        return
    rel = "/" + os.path.relpath(wt_root, top).replace(os.sep, "/") + "/"
    excl = os.path.join(gitdir, "info", "exclude")
    os.makedirs(os.path.dirname(excl), exist_ok=True)
    current = open(excl, encoding="utf-8").read() if os.path.exists(excl) else ""
    if rel not in current.split("\n"):
        with open(excl, "a", encoding="utf-8") as f:
            f.write(("" if current.endswith("\n") or not current else "\n") + f"# worktrees do Commitdeck\n{rel}\n")


def _exclude_copied(wt, files):
    """Os arquivos copiados (segredos locais: workspace.local.json, nuget.config…) NUNCA podem ir para commit — nem por um
    `git add -A` do agente. Vão para o exclude do repositório (vale para os worktrees dele; local, não versionado)."""
    if not files:
        return
    excl = git.run(wt, "rev-parse", "--git-path", "info/exclude").strip()
    excl = excl if os.path.isabs(excl) else os.path.join(wt, excl)
    os.makedirs(os.path.dirname(excl), exist_ok=True)
    current = open(excl, encoding="utf-8").read().split("\n") if os.path.exists(excl) else []
    new = [f"/{f}" for f in files if f"/{f}" not in current]
    if new:
        with open(excl, "a", encoding="utf-8") as fh:
            fh.write(("\n" if current and current[-1] else "") + "# copiados pelo Commitdeck para os worktrees (não versionar)\n" + "\n".join(new) + "\n")


def _copy_untracked(src, dst, patterns):
    """Copia para o worktree os arquivos locais que o Git não leva (só os que existem e não estão versionados)."""
    tracked = set(git.run(src, "ls-files", "-z").split("\0"))
    copied = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [x for x in dirs if x not in {".git", "node_modules", "bin", "obj", ".worktrees", "dist", ".venv"}]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), src).replace(os.sep, "/")
            if rel in tracked or not any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(f, p) and "/" not in p for p in patterns):
                continue
            target = os.path.join(dst, rel)
            if os.path.exists(target):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(root, f), target)
            copied.append(rel)
            if len(copied) > 200:
                return copied
    return copied


def create_task(repo_id, body):
    """Nova tarefa: branch a partir da base, worktree, arquivos locais, preparação e (opcional) agente com o prompt."""
    repo = git.get_repo(repo_id)
    d = _load()
    p = _proj(d, repo_id)
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("Diga o que é a tarefa")
    kind = body.get("kind") or "feature"
    slug = slugify(body.get("slug") or title)
    branch = body.get("branch") or f"{kind}/{slug}"
    git._check_branch(branch)
    base = body.get("base") or _default_base(repo)
    path, copied, wt = _make_worktree(repo, p["settings"], slug, branch, base)
    # mesma tarefa em outros repositórios (ex.: entidades → infra → API): mesmo slug e branch, base padrão de cada um
    linked = []
    for lid in body.get("linked") or []:
        if lid == repo_id:
            continue
        lrepo = git.get_repo(lid)
        lp, _lc, lwt = _make_worktree(lrepo, _proj(d, lid)["settings"], slug, branch, _default_base(lrepo))
        linked.append({"repoId": lid, "name": lrepo["name"], "path": lp, "wtRepoId": lwt["id"]})
    prompt = body.get("prompt") or ""
    if linked:
        prompt += "\n\nEsta tarefa atravessa repositórios — cada um tem um worktree na branch " + branch + ":\n" + \
            "\n".join([f"- {repo['name']}: {path} (este)"] + [f"- {x['name']}: {x['path']}" for x in linked])
    task = {"id": uuid.uuid4().hex[:10], "title": title, "slug": slug, "branch": branch, "base": base, "path": path,
            "repoId": wt["id"], "createdAt": now_iso(), "status": "open", "workItem": body.get("workItem"),
            "prompt": prompt, "copied": copied, "group": body.get("group"), "linked": linked, "reviewOf": body.get("reviewOf")}
    p["tasks"].append(task)
    _save(d)
    if (p["settings"].get("setup") or "").strip():
        terminals.create(path, "preparação", p["settings"]["setup"], "setup", {"project": repo_id, "task": task["id"]})
    agent_ids = body.get("agents") or ([body["agent"]] if body.get("agent") else [])
    for aid in agent_ids:
        start_agent(repo_id, task["id"], aid, task["prompt"] or title, body.get("mode"))
    return task


def _default_base(repo):
    try:
        return git.run(repo["path"], "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    except Exception:  # noqa: BLE001
        return git.status(repo["id"])["branch"] or "HEAD"


def _make_worktree(repo, settings, slug, branch, base):
    path = os.path.join(_worktree_root(repo, settings), slug)
    if os.path.exists(path):
        path = f"{path}-{uuid.uuid4().hex[:4]}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _exclude_from_enclosing_repo(os.path.dirname(os.path.dirname(path)))
    try:
        git.run(repo["path"], "fetch", "origin", "--prune", timeout=180, auth=git.auth_for(repo))
    except Exception:  # noqa: BLE001 — sem rede: segue com o que tem
        pass
    if git.run(repo["path"], "branch", "--list", branch).strip():
        git.run(repo["path"], "worktree", "add", path, branch, timeout=120)
    else:
        git.run(repo["path"], "worktree", "add", "-b", branch, path, git._check_ref(base), timeout=120)
    copied = _copy_untracked(repo["path"], path, settings.get("copy") or [])
    _exclude_copied(path, copied)
    return path, copied, git.add_repo(path)


def _task(d, repo_id, task_id):
    t = next((x for x in _proj(d, repo_id)["tasks"] if x["id"] == task_id), None)
    if not t:
        raise LookupError("Tarefa não encontrada")
    return t


def update_task(repo_id, task_id, body):
    d = _load()
    t = _task(d, repo_id, task_id)
    for k in ("title", "status", "prompt", "pr"):
        if k in body:
            t[k] = body[k]
    _save(d)
    return t


def remove_task(repo_id, task_id, force=False, delete_branch=False):
    d = _load()
    t = _task(d, repo_id, task_id)
    repo = git.get_repo(repo_id)
    for term in terminals.list_all(task=task_id):
        terminals.close(term["id"])
    if os.path.isdir(t["path"]):
        if not force:
            st = git.status(path=t["path"])
            if st["staged"] or st["unstaged"] or st["untracked"] or st["conflicts"]:
                raise ValueError("O worktree tem alterações não commitadas — commite, descarte ou force a remoção")
        git.run(repo["path"], "worktree", "remove", *(["--force"] if force else []), t["path"], timeout=120)
    git.run(repo["path"], "worktree", "prune")
    try:
        git.remove_repo(t["repoId"])
    except Exception:  # noqa: BLE001
        pass
    for x in t.get("linked") or []:
        try:
            lr = git.get_repo(x["repoId"])
            if os.path.isdir(x["path"]):
                git.run(lr["path"], "worktree", "remove", *(["--force"] if force else []), x["path"], timeout=120)
            git.run(lr["path"], "worktree", "prune")
            git.remove_repo(x["wtRepoId"])
            if delete_branch:
                git.run(lr["path"], "branch", "-D" if force else "-d", t["branch"], check=False)
        except Exception as e:  # noqa: BLE001
            if not force:
                raise ValueError(f"{x['name']}: {e}") from None
    if delete_branch:
        try:
            git.run(repo["path"], "branch", "-D" if force else "-d", t["branch"])
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Worktree removido; a branch {t['branch']} ficou: {e}") from None
    _proj(d, repo_id)["tasks"] = [x for x in _proj(d, repo_id)["tasks"] if x["id"] != task_id]
    _save(d)


# ---------------------------------------------------------------- terminais e agentes de um projeto/tarefa
def _cwd(repo_id, task_id=None):
    if task_id:
        return _task(_load(), repo_id, task_id)["path"]
    return git.get_repo(repo_id)["path"]


def _settings(repo_id):
    return _proj(_load(), repo_id)["settings"]


def start_shell(repo_id, task_id=None, title=None, command=None):
    meta = {"project": repo_id, **({"task": task_id} if task_id else {})}
    return terminals.create(_cwd(repo_id, task_id), title or "terminal", command, "shell", meta,
                            shell=_settings(repo_id).get("shell") or None).info()


def start_agent(repo_id, task_id, account_id, prompt=None, mode=None, title=None, resume_sid=None):
    a = agents.get_account(account_id)
    resume = None
    if resume_sid:   # retomar a conversa de uma sessão anterior (o app foi fechado): mesma sessão da CLI
        rec = agents._resume_db().get(resume_sid) or {}
        resume, account_id = rec.get("cliSession"), rec.get("account") or account_id
        a = agents.get_account(account_id)
        agents.forget_resume(resume_sid)
    sid = uuid.uuid4().hex[:12]
    extra = list(_settings(repo_id).get("addDirs") or [])
    if task_id:
        extra += [x["path"] for x in _task(_load(), repo_id, task_id).get("linked") or []]   # tarefa em vários repos
    command, env = agents.launch_spec(account_id, prompt, mode, sid, extra_dirs=extra, resume=resume)
    meta = {"project": repo_id, "account": account_id, "provider": a["provider"], "sid": sid,
            **({"task": task_id} if task_id else {})}
    label = title or f"{agents.PROVIDERS[a['provider']]['label']} · {a['name']}"
    t = terminals.create(_cwd(repo_id, task_id), label, command, "agent", meta, env)
    agents.set_title(sid, label)
    agents.set_meta(sid, projectName=git.get_repo(repo_id)["name"], project=repo_id, task=task_id)
    agents.remember(sid, account=account_id, provider=a["provider"], project=repo_id, task=task_id, title=label,
                    cliSession=resume, started=now_iso())
    return t.info()


# ---------------------------------------------------------------- arquivos
def _root(repo_id, task_id=None):
    return os.path.realpath(_cwd(repo_id, task_id))


def _safe(root, rel):
    full = os.path.realpath(os.path.join(root, rel or ""))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("Caminho fora do projeto")
    return full


def files(repo_id, task_id=None):
    """Todos os arquivos do projeto (versionados + novos não ignorados), como o ⌘P precisa."""
    root = _root(repo_id, task_id)
    out = git.run(root, "ls-files", "-co", "--exclude-standard", "-z", timeout=30)
    names = [x for x in out.split("\0") if x]
    return {"root": root, "files": names[:60000], "truncated": len(names) > 60000}


def read_file(repo_id, rel, task_id=None):
    full = _safe(_root(repo_id, task_id), rel)
    size = os.path.getsize(full)
    if size > MAX_FILE:
        return {"path": rel, "size": size, "tooLarge": True}
    with open(full, "rb") as f:
        raw = f.read()
    if b"\0" in raw[:8000]:
        return {"path": rel, "size": size, "binary": True}
    return {"path": rel, "size": size, "text": raw.decode("utf-8", errors="replace"), "mtime": os.path.getmtime(full),
            "crlf": b"\r\n" in raw[:20000], "root": _root(repo_id, task_id)}


def write_file(repo_id, rel, text, task_id=None, mtime=None):
    full = _safe(_root(repo_id, task_id), rel)
    if mtime and os.path.exists(full) and abs(os.path.getmtime(full) - float(mtime)) > 0.001:
        raise ValueError("O arquivo mudou no disco desde que foi aberto (o agente pode ter editado) — recarregue antes de salvar")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return {"mtime": os.path.getmtime(full)}


def search(repo_id, query, task_id=None, regex=False, case=False, limit=400):
    """Busca no projeto: ripgrep se houver; senão git grep (que já respeita o .gitignore)."""
    root = _root(repo_id, task_id)
    if not query:
        return {"results": []}
    rg = shutil.which("rg") or next((p for p in ("/opt/homebrew/bin/rg", "/usr/local/bin/rg") if os.path.exists(p)), None)
    if rg:
        args = [rg, "--line-number", "--column", "--no-heading", "--color=never", "--max-count=50", "--max-columns=300"]
        args += ([] if case else ["-i"]) + ([] if regex else ["-F"]) + ["--", query, "."]
    else:
        args = ["git", "grep", "-n", "--column", "-I"] + ([] if case else ["-i"]) + ([] if regex else ["-F"]) + ["-e", query]
    r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=30,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    res = []
    for line in r.stdout.splitlines()[:limit]:
        m = re.match(r"^(?:\./)?(.+?):(\d+):(\d+):(.*)$", line)
        if m:
            res.append({"path": m.group(1), "line": int(m.group(2)), "col": int(m.group(3)), "text": m.group(4)[:300]})
    return {"results": res, "truncated": len(r.stdout.splitlines()) > limit}


def diff_summary(repo_id, task_id):
    """Resumo do que a tarefa mudou em relação à base (para revisar antes do PR)."""
    t = _task(_load(), repo_id, task_id)
    base = t["base"]
    try:
        mb = git.run(t["path"], "merge-base", "HEAD", base).strip()
    except Exception:  # noqa: BLE001
        mb = base
    stat = git.run(t["path"], "diff", "--numstat", mb, timeout=60)
    files_ = []
    for line in stat.splitlines():
        a, b, f = (line.split("\t") + ["", "", ""])[:3]
        files_.append({"path": f, "add": int(a) if a.isdigit() else None, "del": int(b) if b.isdigit() else None})
    ahead = git.run(t["path"], "rev-list", "--count", f"{mb}..HEAD").strip()
    return {"base": base, "mergeBase": mb, "files": files_, "commits": int(ahead or 0), "status": git.status(path=t["path"])}



def base_file(repo_id, task_id, rel):
    """Conteúdo do arquivo no ponto em que a tarefa saiu da base (merge-base) — o lado "antes" da revisão."""
    t = _task(_load(), repo_id, task_id)
    _safe(os.path.realpath(t["path"]), rel)
    try:
        mb = git.run(t["path"], "merge-base", "HEAD", t["base"]).strip()
    except Exception:  # noqa: BLE001
        mb = t["base"]
    try:
        text = git.run(t["path"], "show", f"{mb}:{rel}", timeout=30)
        return {"path": rel, "text": text, "exists": True}
    except Exception:  # noqa: BLE001 — arquivo novo na tarefa
        return {"path": rel, "text": "", "exists": False}


def changed_files(repo_id, task_id):
    """Tudo que a tarefa mudou em relação à base: commits + alterações ainda sem commit + arquivos novos."""
    d = diff_summary(repo_id, task_id)
    t = _task(_load(), repo_id, task_id)
    out = git.run(t["path"], "diff", "--numstat", d["mergeBase"], timeout=60)   # base × árvore de trabalho
    files = []
    for line in out.splitlines():
        a, b, f = (line.split("\t") + ["", "", ""])[:3]
        files.append({"path": f, "add": int(a) if a.isdigit() else None, "del": int(b) if b.isdigit() else None, "status": "M"})
    names = {f["path"] for f in files}
    for u in d["status"]["untracked"]:
        if u["path"] not in names:
            files.append({"path": u["path"], "add": None, "del": None, "status": "A"})
    deleted = set(git.run(t["path"], "diff", "--name-only", "--diff-filter=D", d["mergeBase"]).split())
    for f in files:
        if f["path"] in deleted:
            f["status"] = "D"
        elif not git.run(t["path"], "cat-file", "-t", f"{d['mergeBase']}:{f['path']}", check=False).strip():
            f["status"] = "A"
    return {"files": sorted(files, key=lambda x: x["path"]), "base": t["base"], "mergeBase": d["mergeBase"]}
