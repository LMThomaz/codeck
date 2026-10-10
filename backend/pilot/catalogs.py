"""Catálogos de repositórios: agrupam repositórios remotos (de uma organização/projeto do Azure, de uma
organização/conta do GitHub ou avulsos) e mostram, para cada um, se está clonado nesta máquina.

catalogs.json: [{id, name, color, baseDir, sources: [{provider, account, owner, project}], extra: [chave], exclude: [chave]}]
A lista remota de cada origem fica em cache por 10 minutos; o casamento com o clone local é pela URL do remoto
normalizada (https/ssh/.git dão a mesma chave).
"""
import os
import re
import time
import uuid

from . import git
from .core import CATALOGS_FILE, ctx, load_json, save_json

_remote_cache = {}   # (provider, account, owner, project) -> (ts, repos)
COLORS = ["#3F8CF0", "#22C38E", "#F0A23F", "#E5577B", "#8B6CF0", "#2EC4D6", "#F06A3F", "#9AA4B2"]


def load():
    return load_json(CATALOGS_FILE, [])


def save(cats):
    save_json(CATALOGS_FILE, cats)


def _clean_source(s):
    prov = s.get("provider")
    if prov not in ("azure", "github"):
        raise ValueError("origem inválida")
    return {"provider": prov, "account": (s.get("account") or "").strip(), "owner": (s.get("owner") or "").strip() or None,
            "project": (s.get("project") or "").strip() or None}


def upsert(body):
    cats = load()
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Dê um nome ao catálogo")
    cid = body.get("id") or uuid.uuid4().hex[:10]
    entry = {
        "id": cid, "name": name[:60], "color": body.get("color") or COLORS[len(cats) % len(COLORS)],
        "baseDir": os.path.expanduser((body.get("baseDir") or "").strip()) or None,
        "sources": [_clean_source(s) for s in body.get("sources", [])],
        "extra": [str(x) for x in body.get("extra", [])][:500], "exclude": [str(x) for x in body.get("exclude", [])][:500],
        "description": (body.get("description") or "").strip()[:200],
    }
    idx = next((i for i, c in enumerate(cats) if c["id"] == cid), None)
    if idx is None:
        cats.append(entry)
    else:
        cats[idx] = entry
    save(cats)
    return entry


def delete(cid):
    save([c for c in load() if c["id"] != cid])


def _account(provider, account):
    if provider == "azure":
        org = ctx.orgs.get(account) or next(iter(ctx.orgs.values()), None)
        if not org:
            raise ValueError(f"Organização do Azure {account} não está conectada")
        return org
    acc = next((a for a in ctx.gh.values() if a.login.lower() == (account or "").lower()), None) or next(iter(ctx.gh.values()), None)
    if not acc:
        raise ValueError("Nenhuma conta do GitHub conectada")
    return acc


def remote_repos(source, force=False):
    k = (source["provider"], source["account"], source.get("owner"), source.get("project"))
    if not force and k in _remote_cache and time.time() - _remote_cache[k][0] < 600:
        return _remote_cache[k][1]
    acc = _account(source["provider"], source["account"])
    repos = acc.list_repos(source.get("project")) if source["provider"] == "azure" else acc.list_repos(source.get("owner"))
    _remote_cache[k] = (time.time(), repos)
    return repos


def local_index():
    """remoteKey normalizada -> repositório local registrado (com status resumido)."""
    out = {}
    for r in git.list_repos(with_status=True):
        if r.get("remoteKey"):
            out[r["remoteKey"]] = r
    return out


def view(cid, force=False):
    cat = next((c for c in load() if c["id"] == cid), None)
    if not cat:
        raise ValueError("Catálogo não encontrado")
    repos, errors, seen = [], {}, set()
    for s in cat["sources"]:
        try:
            for r in remote_repos(s, force):
                if r["key"] not in seen:
                    seen.add(r["key"])
                    repos.append(r)
        except Exception as e:  # noqa: BLE001
            errors[f"{s['provider']}:{s.get('owner') or s.get('project') or s['account']}"] = str(e)[:240]
    exclude = set(cat.get("exclude") or [])
    repos = [r for r in repos if r["key"] not in exclude]
    local = local_index()
    if cat.get("baseDir") and adopt_existing(cat["baseDir"], repos, local):
        local = local_index()
    for r in repos:
        lk = git.normalize_remote(r.get("cloneUrl") or r.get("sshUrl") or "")
        loc = local.get(lk)
        r["remoteKey"] = lk
        r["local"] = {k: loc.get(k) for k in ("id", "path", "status", "lastCommit", "exists", "pinned")} if loc else None
        r["cloned"] = bool(loc and loc.get("exists"))
        r["clonePath"] = os.path.join(cat["baseDir"], r["name"]) if cat.get("baseDir") else None
    repos.sort(key=lambda r: (not r["cloned"], (r.get("updated") or "") == "", (r.get("name") or "").lower()))
    return {**cat, "repos": repos, "errors": errors, "counts": {"total": len(repos), "cloned": sum(r["cloned"] for r in repos)}}


def adopt_existing(base, repos, local):
    """Clones que já existem na pasta-base (feitos fora do app) entram no registro sozinhos."""
    wanted = {git.normalize_remote(r.get("cloneUrl") or r.get("sshUrl") or ""): r for r in repos}
    candidates = [base] + [os.path.join(base, r["name"]) for r in repos]
    adopted = False
    for path in candidates:
        if not os.path.exists(os.path.join(path, ".git")):
            continue
        try:
            key = git.normalize_remote(git.remote_info(path).get("remoteUrl"))
        except Exception:  # noqa: BLE001
            continue
        if key in wanted and key not in local:
            git.add_repo(path)
            adopted = True
    return adopted


def suggestions():
    """Um catálogo sugerido por organização/projeto do Azure e por organização/conta do GitHub conectados."""
    out = []
    for name, org in ctx.orgs.items():
        try:
            for p in org.projects():
                out.append({"name": p["name"] if p["name"].lower() != name.lower() else name,
                            "sources": [{"provider": "azure", "account": name, "project": p["name"]}],
                            "label": f"Azure · {name} / {p['name']}"})
        except Exception:  # noqa: BLE001
            continue
    for acc in ctx.gh.values():
        try:
            me = acc.identity()
            out.append({"name": me["login"], "sources": [{"provider": "github", "account": acc.login, "owner": me["login"]}],
                        "label": f"GitHub · @{me['login']} (pessoal)"})
            for o in acc.orgs():
                out.append({"name": o["login"], "sources": [{"provider": "github", "account": acc.login, "owner": o["login"]}],
                            "label": f"GitHub · {o['login']}", "avatar": o.get("avatar")})
        except Exception:  # noqa: BLE001
            continue
    names = {c["name"].lower() for c in load()}
    for s in out:
        s["exists"] = s["name"].lower() in names
    return out


def clone(cid, repo_key, dest=None):
    cat = view(cid)
    r = next((x for x in cat["repos"] if x["key"] == repo_key), None)
    if not r:
        raise ValueError("Repositório não está no catálogo")
    if r["cloned"]:
        raise ValueError("Já está clonado")
    dest = dest or r.get("clonePath")
    if not dest:
        raise ValueError("Defina a pasta onde clonar (pasta-base do catálogo)")
    url = r.get("cloneUrl")
    if r["provider"] == "azure" and url:
        url = re.sub(r"^https://[^@/]+@", "https://", url)   # o Azure põe o usuário na URL; a credencial vai pelo header
    info = git.parse_remote(url)
    return git.clone(url, dest, auth=git._auth_lookup["fn"](info.get("provider"), info.get("owner")) if git._auth_lookup["fn"] else None)
