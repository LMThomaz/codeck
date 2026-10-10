"""Catálogos de repositórios: agrupam repositórios remotos (de uma organização/projeto do Azure, de uma
organização/conta do GitHub ou avulsos) e mostram, para cada um, se está clonado nesta máquina.

catalogs.json: [{id, name, color, baseDir, sources: [{provider, account, owner, project}], extra: [chave], exclude: [chave]}]
Catálogos são MANUAIS (categorias do usuário). Cada CONTA conectada é, por si, a lista de todos os repositórios dela
(account_view) — não vira catálogo.

A lista remota de cada origem fica em cache (remote-cache.json, em disco): é relida após 10 minutos, mas a última
lista boa continua valendo sem internet e alimenta os contadores do painel. O casamento com o clone local é pela URL
do remoto normalizada (https/ssh/.git dão a mesma chave).
"""
import os
import re
import time
import uuid

from . import git
import threading

from .core import CATALOGS_FILE, DATA, ctx, is_network_error, load_json, save_json

CACHE_FILE = os.path.join(DATA, "remote-cache.json")
ACCOUNT_DIRS_FILE = os.path.join(DATA, "account-dirs.json")   # "provider:conta" -> pasta onde clonar
_cache_lock = threading.Lock()
_remote_cache = None   # "provider|conta|owner|projeto" -> [ts, repos]; carregado do disco na 1ª vez
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


def _cache():
    global _remote_cache
    if _remote_cache is None:
        _remote_cache = load_json(CACHE_FILE, {})
    return _remote_cache


def _ckey(source):
    return "|".join(str(source.get(k) or "") for k in ("provider", "account", "owner", "project")).lower()


def cached(source):
    hit = _cache().get(_ckey(source))
    return hit[1] if hit else None


def fetch(source, force=False):
    """(repos, desde_quando_sem_atualizar | None). Sem internet, devolve a última lista boa (marcada como antiga)."""
    k = _ckey(source)
    hit = _cache().get(k)
    if not force and hit and time.time() - hit[0] < 600:
        return hit[1], None
    try:
        acc = _account(source["provider"], source["account"])
        repos = acc.list_repos(source.get("project")) if source["provider"] == "azure" else acc.list_repos(source.get("owner"))
    except Exception as e:  # noqa: BLE001
        if hit and is_network_error(e):
            return hit[1], hit[0]
        raise
    with _cache_lock:
        _cache()[k] = [time.time(), repos]
        save_json(CACHE_FILE, _cache())
    return repos, None


def remote_repos(source, force=False):
    return fetch(source, force)[0]


# ---------------------------------------------------------------- pastas de trabalho (várias pastas base)
# Os clones vivem espalhados (…/cifal/apis, …/cifal/mobile…). Pastas de trabalho = as configuradas em Preferências +
# as pastas onde já há repositórios registrados. Elas servem para (1) reconhecer sozinho clones feitos fora do app e
# (2) oferecer o destino na hora de clonar.
_discover = {"at": 0.0}


def workspace_roots():
    return [os.path.expanduser(p) for p in (ctx.config.get("workspaceRoots") or []) if p]


def clone_targets():
    """Destinos sugeridos para clonar: pastas configuradas e pastas que já têm clones, com quantos repositórios cada uma tem."""
    counts = {}
    for r in git.list_repos(with_status=False):
        if r.get("exists"):
            parent = os.path.dirname(r["path"].rstrip(os.sep))
            counts[parent] = counts.get(parent, 0) + 1
    out = [{"path": p, "count": counts.pop(p, 0), "configured": True} for p in workspace_roots()]
    out += [{"path": p, "count": n, "configured": False} for p, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    home = os.path.expanduser("~")
    for t in out:
        t["label"] = os.path.basename(t["path"].rstrip(os.sep)) or t["path"]
        t["short"] = t["path"].replace(home, "~", 1)
    return out


def discover(force=False):
    """Registra os repositórios encontrados nas pastas de trabalho (no máximo a cada 2 min)."""
    if not force and time.time() - _discover["at"] < 120:
        return
    _discover["at"] = time.time()
    for t in clone_targets():
        try:
            git.scan(t["path"], depth=2 if t["configured"] else 1)
        except Exception:  # noqa: BLE001 — pasta removida ou sem permissão
            continue


def local_index():
    """remoteKey normalizada -> repositório local registrado (com status resumido)."""
    out = {}
    for r in git.list_repos(with_status=True):
        if r.get("remoteKey"):
            out[r["remoteKey"]] = r
    return out


def _build(meta, sources, exclude=(), base_dir=None, force=False):
    repos, errors, seen, stale = [], {}, set(), None
    for s in sources:
        try:
            got, old = fetch(s, force)
            stale = min(stale or old, old) if old else stale
            for r in got:
                if r["key"] not in seen:
                    seen.add(r["key"])
                    repos.append(r)
        except Exception as e:  # noqa: BLE001
            label = f"{s['provider']}:{s.get('owner') or s.get('project') or s['account']}"
            errors[label] = "sem conexão — a lista aparece quando a internet voltar" if is_network_error(e) else str(e)[:240]
    exclude = set(exclude or [])
    repos = [dict(r) for r in repos if r["key"] not in exclude]
    discover()
    local = local_index()
    if base_dir and adopt_existing(base_dir, repos, local):
        local = local_index()
    for r in repos:
        lk = git.normalize_remote(r.get("cloneUrl") or r.get("sshUrl") or "")
        loc = local.get(lk)
        r["remoteKey"] = lk
        r["local"] = {k: loc.get(k) for k in ("id", "path", "status", "lastCommit", "exists", "pinned")} if loc else None
        r["cloned"] = bool(loc and loc.get("exists"))
        r["clonePath"] = os.path.join(base_dir, r["name"]) if base_dir else None
    repos.sort(key=lambda r: (not r["cloned"], (r.get("updated") or "") == "", (r.get("name") or "").lower()))
    return {**meta, "baseDir": base_dir, "repos": repos, "errors": errors, "staleSince": stale,
            "counts": {"total": len(repos), "cloned": sum(r["cloned"] for r in repos)}}


def view(cid, force=False):
    if cid and cid.startswith("account:"):
        return account_view(cid[8:], force)
    cat = next((c for c in load() if c["id"] == cid), None)
    if not cat:
        raise ValueError("Catálogo não encontrado")
    return _build(cat, cat["sources"], cat.get("exclude"), cat.get("baseDir"), force)


# ---------------------------------------------------------------- contas: todos os repositórios de cada uma
def accounts():
    return [{"key": f"{p}:{n}", "provider": p, "name": n} for p, n in _connected()]


def _account_source(key):
    prov, _, name = key.partition(":")
    if (prov, name) not in _connected():
        raise ValueError("Conta não está conectada")
    return {"provider": prov, "account": name, "owner": None, "project": None}


def account_view(key, force=False):
    prov, _, name = key.partition(":")
    meta = {"id": "account:" + key, "name": name, "provider": prov, "account": True, "sources": [_account_source(key)],
            "color": "", "extra": [], "exclude": []}
    return _build(meta, meta["sources"], (), load_json(ACCOUNT_DIRS_FILE, {}).get(key), force)


def set_account_dir(key, base):
    dirs = load_json(ACCOUNT_DIRS_FILE, {})
    dirs[key] = os.path.expanduser((base or "").strip()) or None
    save_json(ACCOUNT_DIRS_FILE, dirs)


def summary():
    """Catálogos e contas com a contagem de repositórios — do cache; None enquanto a lista ainda não foi lida."""
    def count(sources, exclude=()):
        keys = set()
        for s in sources:
            got = cached(s)
            if got is None:
                return None
            keys |= {r["key"] for r in got}
        return len(keys - set(exclude or []))
    return {"catalogs": [{**c, "count": count(c["sources"], c.get("exclude"))} for c in load()],
            "accounts": [{**a, "count": count([_account_source(a["key"])])} for a in accounts()]}


def warm():
    """Lê (se o cache estiver velho) a lista de cada conta e de cada catálogo — os contadores do painel saem daqui."""
    srcs = [_account_source(a["key"]) for a in accounts()] + [s for c in load() for s in c["sources"]]
    for s in srcs:
        try:
            fetch(s)
        except Exception:  # noqa: BLE001 — sem rede ou sem permissão: o contador só fica vazio
            continue


def warm_async():
    threading.Thread(target=warm, daemon=True).start()


def cleanup_auto():
    """A 2.0.0+10 criava um catálogo por projeto/org ao conectar a conta; agora a conta lista tudo e os catálogos são
    só os do usuário. Remove os automáticos (marcados com "auto") e o registro deles."""
    cats = load()
    keep = [c for c in cats if not c.get("auto")]
    if len(keep) != len(cats):
        save(keep)
    if os.path.exists(os.path.join(DATA, "catalogs-auto.json")):
        os.remove(os.path.join(DATA, "catalogs-auto.json"))


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


def _account_suggestions(provider, name):
    """Catálogos naturais de UMA conta: um por projeto do Azure; no GitHub, o pessoal e um por organização."""
    out = []
    if provider == "azure":
        org = ctx.orgs[name]
        for p in org.projects():
            out.append({"name": p["name"] if p["name"].lower() != name.lower() else name,
                        "sources": [{"provider": "azure", "account": name, "owner": None, "project": p["name"]}],
                        "label": f"Azure · {name} / {p['name']}"})
    else:
        acc = next(a for a in ctx.gh.values() if a.login == name)
        me = acc.identity()
        out.append({"name": me["login"], "sources": [{"provider": "github", "account": acc.login, "owner": me["login"], "project": None}],
                    "label": f"GitHub · @{me['login']} (pessoal)"})
        for o in acc.orgs():
            out.append({"name": o["login"], "sources": [{"provider": "github", "account": acc.login, "owner": o["login"], "project": None}],
                        "label": f"GitHub · {o['login']}", "avatar": o.get("avatar")})
    return out


def _connected():
    return [("azure", n) for n in ctx.orgs] + [("github", a.login) for a in ctx.gh.values()]


def suggestions():
    """Um catálogo sugerido por organização/projeto do Azure e por organização/conta do GitHub conectados."""
    out = []
    for prov, name in _connected():
        try:
            out.extend(_account_suggestions(prov, name))
        except Exception:  # noqa: BLE001
            continue
    names = {c["name"].lower() for c in load()}
    for s in out:
        s["exists"] = s["name"].lower() in names
    return out


def clone(cid, repo_key, dest=None):
    cat = view(cid)   # "account:<provider:conta>" também vale
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
