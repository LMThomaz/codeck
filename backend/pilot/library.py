"""Favoritos e tags: uma coleção pessoal de repositórios de QUALQUER conta conectada (GitHub e Azure misturados).

Cada favorito leva tags livres ("Open-Source", "Sustentação"…); cada tag funciona como um catálogo — aparece nas
coleções e lista os favoritos que a têm. Tag nova é criada no momento em que é usada, com a próxima cor da paleta.

library.json: {"repos": [{key, provider, account, owner, name, fullName, cloneUrl, sshUrl, webUrl, description,
                          private, tags: [nome], addedAt}],
               "tags": [{name, color, baseDir}]}
A chave do favorito é a do remoto normalizado (git.normalize_remote) — a mesma que casa catálogo e clone local; um
repositório local sem remoto usa "local:<id>". Guardamos um retrato do remoto para listar sem ir à rede.
"""
import os
import re

from . import catalogs, git
from .core import LIBRARY_FILE, ctx, is_network_error, load_json, now_iso, save_json

COLORS = ["#6F8CFF", "#3CCF91", "#F5B84F", "#FF6B7D", "#B07CFF", "#4FC3F7", "#FF8A50", "#9AA4B2", "#E879F9", "#A3E635"]
SNAPSHOT = ("provider", "account", "owner", "name", "fullName", "cloneUrl", "sshUrl", "webUrl", "description", "private", "defaultBranch")


def _load():
    d = load_json(LIBRARY_FILE, {})
    return {"repos": d.get("repos") or [], "tags": d.get("tags") or []}


def _save(d):
    save_json(LIBRARY_FILE, d)


def _clean_tag(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:40]
    if not name:
        raise ValueError("Tag vazia")
    return name


def _ensure_tags(d, names):
    """Devolve os nomes canônicos (respeitando a grafia de uma tag que já existe) e cria as que faltam."""
    out = []
    for n in names:
        n = _clean_tag(n)
        hit = next((t for t in d["tags"] if t["name"].lower() == n.lower()), None)
        if not hit:
            hit = {"name": n, "color": COLORS[len(d["tags"]) % len(COLORS)], "baseDir": None}
            d["tags"].append(hit)
        if hit["name"] not in out:
            out.append(hit["name"])
    return out


def key_of(repo):
    if repo.get("key", "").startswith("local:"):
        return repo["key"]
    url = repo.get("cloneUrl") or repo.get("sshUrl") or repo.get("remoteUrl") or ""
    return repo.get("remoteKey") or (git.normalize_remote(url) if url else repo.get("key"))


def _enrich(items):
    local = catalogs.local_index()
    by_id = {r["id"]: r for r in git.list_repos(with_status=True)} if any(i["key"].startswith("local:") for i in items) else {}
    out = []
    for it in items:
        loc = by_id.get(it["key"][6:]) if it["key"].startswith("local:") else local.get(it["key"])
        r = {**it, "remoteKey": it["key"], "cloned": bool(loc and loc.get("exists")),
             "local": {k: loc.get(k) for k in ("id", "path", "status", "lastCommit", "exists", "pinned", "name")} if loc else None}
        out.append(r)
    out.sort(key=lambda r: (not r["cloned"], (r.get("name") or "").lower()))
    return out


def view():
    d = _load()
    repos = _enrich(d["repos"])
    counts = {}
    for r in d["repos"]:
        for t in r.get("tags") or []:
            counts[t] = counts.get(t, 0) + 1
    return {"repos": repos, "tags": [{**t, "count": counts.get(t["name"], 0)} for t in d["tags"]]}


def favorite(body):
    """{repo: retrato do repositório (remoto do catálogo/busca ou local), on: bool, tags?: [nomes]}"""
    src = body.get("repo") or {}
    key = key_of(src)
    if not key:
        raise ValueError("Repositório sem identificação")
    d = _load()
    d["repos"] = [r for r in d["repos"] if r["key"] != key] if not body.get("on", True) else d["repos"]
    if body.get("on", True):
        cur = next((r for r in d["repos"] if r["key"] == key), None)
        snap = {k: src.get(k) for k in SNAPSHOT}
        if not snap.get("cloneUrl") and src.get("remoteUrl"):
            snap["cloneUrl"] = src["remoteUrl"]
        if not snap.get("fullName"):
            snap["fullName"] = src.get("slug") or src.get("name")
        tags = _ensure_tags(d, body.get("tags") or [])
        if cur:
            cur.update({k: v for k, v in snap.items() if v not in (None, "")})
            cur["tags"] = list(dict.fromkeys((cur.get("tags") or []) + tags))
        else:
            d["repos"].append({"key": key, **snap, "tags": tags, "addedAt": now_iso()})
    _save(d)
    return {"key": key}


def set_tags(body):
    d = _load()
    r = next((x for x in d["repos"] if x["key"] == body.get("key")), None)
    if not r:
        raise ValueError("Favorite o repositório antes de pôr tags")
    r["tags"] = _ensure_tags(d, body.get("tags") or [])
    _save(d)
    return {"tags": r["tags"]}


def save_tag(body):
    """Edita uma tag: nome (renomeia em todos os favoritos), cor e pasta onde clonar os repositórios dela."""
    d = _load()
    old = body.get("name")
    t = next((x for x in d["tags"] if x["name"] == old), None)
    if not t:
        raise ValueError("Tag não encontrada")
    new = _clean_tag(body.get("rename") or old)
    if new.lower() != old.lower() and any(x["name"].lower() == new.lower() for x in d["tags"]):
        raise ValueError(f"Já existe a tag {new}")
    t["name"] = new
    if body.get("color"):
        t["color"] = str(body["color"])[:20]
    if "baseDir" in body:
        t["baseDir"] = os.path.expanduser((body.get("baseDir") or "").strip()) or None
    for r in d["repos"]:
        r["tags"] = [new if x == old else x for x in r.get("tags") or []]
    _save(d)
    return t


def delete_tag(name):
    d = _load()
    d["tags"] = [t for t in d["tags"] if t["name"] != name]
    for r in d["repos"]:
        r["tags"] = [x for x in r.get("tags") or [] if x != name]
    _save(d)


def search(q, force=False):
    """Busca em TODAS as contas conectadas (todas as orgs/projetos do Azure e tudo que o GitHub dá acesso)."""
    q = (q or "").strip().lower()
    sources = [{"provider": "azure", "account": n, "owner": None, "project": None} for n in ctx.orgs] + \
              [{"provider": "github", "account": a.login, "owner": None, "project": None} for a in ctx.gh.values()]
    found, errors, seen = [], {}, set()
    for s in sources:
        try:
            for r in catalogs.remote_repos(s, force):
                if r["key"] in seen:
                    continue
                seen.add(r["key"])
                if not q or q in f"{r.get('fullName')} {r.get('owner')} {r.get('description') or ''}".lower():
                    found.append(r)
        except Exception as e:  # noqa: BLE001 — uma conta fora do ar não esconde as outras
            errors[f"{s['provider']}:{s['account']}"] = "sem conexão" if is_network_error(e) else str(e)[:200]
    favs = {r["key"] for r in _load()["repos"]}
    found.sort(key=lambda r: (not (r.get("name") or "").lower().startswith(q), (r.get("fullName") or "").lower()))
    out = []
    for r in found[:60]:
        k = git.normalize_remote(r.get("cloneUrl") or r.get("sshUrl") or "")
        out.append({**r, "remoteKey": k, "favorite": k in favs})
    return {"repos": out, "errors": errors, "total": len(found)}


def clone(key, dest):
    r = next((x for x in _load()["repos"] if x["key"] == key), None)
    if not r:
        raise ValueError("Não está nos favoritos")
    if not dest:
        raise ValueError("Escolha a pasta onde clonar")
    url = r.get("cloneUrl")
    if not url:
        raise ValueError("Este favorito não tem URL de clone")
    if r.get("provider") == "azure":
        url = re.sub(r"^https://[^@/]+@", "https://", url)   # o Azure põe o usuário na URL; a credencial vai pelo header
    info = git.parse_remote(url)
    return git.clone(url, dest, auth=git._auth_lookup["fn"](info.get("provider"), info.get("owner")) if git._auth_lookup["fn"] else None)
