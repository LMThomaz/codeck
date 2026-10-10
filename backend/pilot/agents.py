"""Agentes de IA: contas (Claude Code, Codex, cursor-agent, Gemini CLI, OpenCode…), como abrir cada um num terminal e
a telemetria de cada sessão — contexto usado, custo, limite de uso e quando ele reseta.

Conta = uma pasta de configuração isolada. Claude: CLAUDE_CONFIG_DIR (~/.claude, ~/.claude-cifal…). Codex: CODEX_HOME.
As credenciais ficam onde a própria CLI guarda (Keychain/arquivo dela) — o app nunca lê token de IA.

Telemetria:
  · Claude Code: o app abre a sessão com --settings contendo uma linha de status e hooks que fazem POST no servidor
    local (/hook/<sessão>/<segredo>) com o JSON que o Claude entrega: modelo, janela de contexto (% usado), custo e,
    quando o plano tem, rate_limits (5 h / semanal, % e reset). Os hooks dizem quando ele está trabalhando, quando
    terminou e quando precisa de você. O segredo é por sessão e só vale para essa rota: o terminal não ganha acesso à API.
  · Codex: lê o log da sessão (CODEX_HOME/sessions/AAAA/MM/DD/*.jsonl), eventos token_count — contexto
    (last_token_usage / model_context_window) e rate_limits (primary/secondary).
  · Demais: só o estado pelo terminal (saindo texto = trabalhando).
"""
import glob
import json
import os
import secrets as pysecrets
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from .core import DATA, DEFAULT_PORT, ctx, load_json, notify, now_iso, save_json

ACCOUNTS_FILE = os.path.join(DATA, "ai-accounts.json")
USAGE_FILE = os.path.join(DATA, "ai-usage.json")   # última leitura de limites por conta (sobrevive ao reinício)
HOME = os.path.expanduser("~")

PROVIDERS = {
    "claude": {"label": "Claude Code", "bin": "claude", "env": "CLAUDE_CONFIG_DIR", "home": ".claude", "telemetry": "hooks"},
    "codex": {"label": "Codex", "bin": "codex", "env": "CODEX_HOME", "home": ".codex", "telemetry": "log"},
    "cursor": {"label": "Cursor Agent", "bin": "cursor-agent", "env": None, "home": ".cursor", "telemetry": None},
    "gemini": {"label": "Gemini CLI", "bin": "gemini", "env": None, "home": ".gemini", "telemetry": None},
    "opencode": {"label": "OpenCode", "bin": "opencode", "env": None, "home": ".config/opencode", "telemetry": None},
}

# ---------------------------------------------------------------- binários (PATH do shell de login, não o do app)
_which = {"at": 0, "map": {}}


def which_all():
    """O app aberto pelo Finder tem PATH mínimo; o shell de login sabe onde estão claude/codex (nvm, ~/.local/bin…)."""
    if time.time() - _which["at"] < 300:
        return _which["map"]
    names = [p["bin"] for p in PROVIDERS.values()]
    found = {}
    if os.name == "nt":
        found = {n: shutil.which(n) for n in names}
    else:
        sh = os.environ.get("SHELL") or "/bin/zsh"
        try:
            out = subprocess.run([sh, "-l", "-c", "; ".join(f"command -v {n} || echo" for n in names)],
                                 capture_output=True, text=True, timeout=15).stdout.splitlines()
            lines = [l.strip() for l in out if l.strip() == "" or l.strip().startswith("/")]
            found = {n: (lines[i] if i < len(lines) and lines[i] else None) for i, n in enumerate(names)}
        except Exception:  # noqa: BLE001
            found = {n: shutil.which(n) for n in names}
    _which.update(at=time.time(), map=found)
    return found


# ---------------------------------------------------------------- contas
def _claude_email(d):
    cj = os.path.join(HOME, ".claude.json") if d == os.path.join(HOME, ".claude") else os.path.join(d, ".claude.json")
    try:
        return (load_json(cj, {}).get("oauthAccount") or {}).get("emailAddress")
    except Exception:  # noqa: BLE001
        return None


def detect():
    """Pastas de configuração encontradas na máquina (sem ler credencial nenhuma)."""
    out = []
    for prov, spec in PROVIDERS.items():
        base = os.path.join(HOME, spec["home"])
        dirs = [base] + (sorted(glob.glob(base + "-*")) if spec["env"] else [])
        for d in dirs:
            if not os.path.isdir(d):
                continue
            suffix = os.path.basename(d)[len(os.path.basename(base)):].lstrip("-")
            email = _claude_email(d) if prov == "claude" else None
            out.append({"provider": prov, "dir": d, "name": suffix or "padrão", "email": email})
    return out


def _load():
    return load_json(ACCOUNTS_FILE, {"accounts": [], "imported": False})


def accounts():
    """Contas configuradas. Na 1ª vez, importa tudo que foi detectado."""
    d = _load()
    if not d.get("imported"):
        for x in detect():
            d["accounts"].append({"id": uuid.uuid4().hex[:10], **x, "color": None})
        d["imported"] = True
        save_json(ACCOUNTS_FILE, d)
    bins = which_all()
    usage = {aid: u for aid, u in _usage.items()}
    out = []
    for a in d["accounts"]:
        spec = PROVIDERS.get(a["provider"], {})
        out.append({**a, "label": spec.get("label"), "installed": bool(bins.get(spec.get("bin"))),
                    "telemetry": spec.get("telemetry"), "usage": usage.get(a["id"])})
    return {"accounts": out, "providers": {k: {"label": v["label"], "installed": bool(bins.get(v["bin"]))} for k, v in PROVIDERS.items()},
            "defaults": d.get("defaults", {})}


def save_account(body):
    d = _load()
    prov = body.get("provider")
    if prov not in PROVIDERS:
        raise ValueError("Provedor desconhecido")
    folder = os.path.abspath(os.path.expanduser((body.get("dir") or "").strip() or os.path.join(HOME, PROVIDERS[prov]["home"])))
    entry = {"id": body.get("id") or uuid.uuid4().hex[:10], "provider": prov, "dir": folder,
             "name": (body.get("name") or "").strip()[:40] or os.path.basename(folder),
             "email": _claude_email(folder) if prov == "claude" else body.get("email"), "color": body.get("color")}
    d["accounts"] = [a for a in d["accounts"] if a["id"] != entry["id"]] + [entry]
    save_json(ACCOUNTS_FILE, d)
    return entry


def delete_account(aid):
    d = _load()
    d["accounts"] = [a for a in d["accounts"] if a["id"] != aid]
    save_json(ACCOUNTS_FILE, d)


def set_default(scope, aid):
    """Conta padrão por escopo: "*" (geral) ou a org/dono do repositório (ex.: "azure:GlorySoft")."""
    d = _load()
    d.setdefault("defaults", {})[scope] = aid
    save_json(ACCOUNTS_FILE, d)


def default_for(scope):
    defs = _load().get("defaults", {})
    return defs.get(scope) or defs.get("*")


def get_account(aid):
    a = next((x for x in _load()["accounts"] if x["id"] == aid), None)
    if not a:
        raise LookupError("Conta de IA não encontrada")
    return a


# ---------------------------------------------------------------- abrir uma sessão de agente
_sessions = {}   # sessão (id do terminal) -> {account, secret, status, statusline, events…}
_usage = load_json(USAGE_FILE, {})   # conta -> {rateLimits, updated, source, plan}
_lock = threading.Lock()


def _hook_cmd(sid, secret):
    url = f"http://127.0.0.1:{getattr(ctx, 'port', None) or DEFAULT_PORT}/hook/{sid}/{secret}"
    return f"curl -s -m 2 -X POST -H 'Content-Type: application/json' --data-binary @- {url}" if os.name != "nt" else \
        f"curl.exe -s -m 2 -X POST -H \"Content-Type: application/json\" --data-binary @- {url}"


def launch_spec(aid, prompt=None, mode=None, sid=None):
    """Comando + variáveis de ambiente para abrir o agente desta conta. `sid` = id da sessão (para a telemetria)."""
    a = get_account(aid)
    prov, spec = a["provider"], PROVIDERS[a["provider"]]
    env = {}
    if spec["env"] and os.path.normpath(a["dir"]) != os.path.join(HOME, spec["home"]):
        env[spec["env"]] = a["dir"]   # a pasta padrão (~/.claude, ~/.codex) é a que a CLI já usa sem variável
    args = [spec["bin"]]
    secret = pysecrets.token_urlsafe(18)
    if prov == "claude":
        post = _hook_cmd(sid, secret)
        status_cmd = (f"{post} >/dev/null 2>&1; echo 'Commitdeck'" if os.name != "nt" else f"{post} >NUL 2>&1 & echo Commitdeck")
        settings = {"statusLine": {"type": "command", "command": status_cmd, "padding": 0},
                    "hooks": {ev: [{"hooks": [{"type": "command", "command": post}]}]
                              for ev in ("UserPromptSubmit", "Stop", "Notification", "SubagentStop", "SessionStart", "PreCompact")}}
        args += ["--settings", json.dumps(settings)]
        if mode in ("plan", "acceptEdits", "default"):
            args += ["--permission-mode", mode]
    elif prov == "codex" and mode == "readonly":
        args += ["--sandbox", "read-only"]
    if prompt:
        args.append(prompt)
    command = " ".join(shlex.quote(x) for x in args) if os.name != "nt" else subprocess.list2cmdline(args)
    with _lock:
        _sessions[sid] = {"account": aid, "provider": prov, "secret": secret, "status": "starting", "started": time.time(),
                          "statusline": None, "events": [], "context": None, "model": None, "cost": None}
    return command, env


# ---------------------------------------------------------------- telemetria
def hook(sid, secret, payload):
    """Recebe a linha de status e os hooks do Claude Code de uma sessão. Valida o segredo da sessão."""
    import hmac
    s = _sessions.get(sid)
    if not s or not hmac.compare_digest(secret or "", s["secret"]):
        raise PermissionError("sessão desconhecida")
    ev = payload.get("hook_event_name")
    with _lock:
        if ev:
            s["events"] = (s["events"] + [{"at": now_iso(), "event": ev, "message": payload.get("message")}])[-30:]
            s["claudeSession"] = payload.get("session_id") or s.get("claudeSession")
            s["status"] = {"UserPromptSubmit": "working", "SessionStart": "idle", "Stop": "done", "SubagentStop": s["status"],
                           "Notification": "needs-you", "PreCompact": "compacting"}.get(ev, s["status"])
            s["statusAt"] = time.time()
        else:   # linha de status
            cw = payload.get("context_window") or {}
            s["model"] = (payload.get("model") or {}).get("display_name") or s["model"]
            cu = cw.get("current_usage") or {}
            s["context"] = {"used": cw.get("used_percentage"), "size": cw.get("context_window_size"),
                            "tokens": sum(v for k, v in cu.items() if isinstance(v, (int, float)) and "input" in k) if cu else None}
            s["cost"] = (payload.get("cost") or {}).get("total_cost_usd")
            s["claudeSession"] = payload.get("session_id") or s.get("claudeSession")
            rl = payload.get("rate_limits")
            if rl:
                lim = _norm_claude_limits(rl)
                if lim:
                    _usage[s["account"]] = {"rateLimits": lim, "updated": now_iso(), "source": "claude"}
                    save_json(USAGE_FILE, _usage)
    if ev == "Notification":
        notify("Agente precisa de você", s.get("title") or "", (payload.get("message") or "")[:140], target=f"term/{sid}")
    elif ev == "Stop":
        notify("Agente terminou", s.get("title") or "", "Pronto para revisar", target=f"term/{sid}")
    return {"ok": True}


def _norm_claude_limits(rl):
    """Medido na linha de status do Claude Code 2.1.296: {"five_hour": {"used_percentage": 48, "resets_at": <epoch s>},
    "seven_day": {...}}. Aceita também a forma {utilization, resets_at ISO} que aparece em outras partes da CLI."""
    out = []
    for key, label in (("five_hour", "5 h"), ("seven_day", "semanal"), ("seven_day_opus", "semanal Opus"), ("seven_day_sonnet", "semanal Sonnet")):
        w = rl.get(key) or {}
        used = w.get("used_percentage", w.get("utilization"))
        if used is None:
            continue
        reset = w.get("resets_at")
        if isinstance(reset, (int, float)):
            reset = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(reset))
        out.append({"window": label, "used": used, "resetsAt": reset})
    return out


def _codex_scan(a, since=0):
    """Último token_count dos logs desta conta do Codex (sessões a partir de `since`)."""
    root = os.path.join(a["dir"], "sessions")
    files = sorted(glob.glob(os.path.join(root, "*", "*", "*", "*.jsonl")), key=os.path.getmtime, reverse=True)[:6]
    for f in files:
        if os.path.getmtime(f) < since:
            break
        last, cwd = None, None
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"token_count"' not in line and '"session_meta"' not in line:
                        continue
                    o = json.loads(line)
                    p = o.get("payload") or {}
                    if o.get("type") == "session_meta":
                        cwd = p.get("cwd")
                    elif p.get("type") == "token_count":
                        last = p
        except (OSError, ValueError):
            continue
        if last:
            return last, cwd, os.path.getmtime(f)
    return None, None, 0


def _norm_codex_limits(rl):
    out = []
    for key, label in (("primary", "5 h"), ("secondary", "semanal")):
        w = (rl or {}).get(key)
        if not w:
            continue
        reset = w.get("resets_at")
        if reset is None and w.get("resets_in_seconds") is not None:
            reset = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + float(w["resets_in_seconds"])))
        elif isinstance(reset, (int, float)):
            reset = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(reset))
        mins = w.get("window_minutes")
        out.append({"window": (f"{mins // 60} h" if mins and mins < 1440 else "semanal") if mins else label,
                    "used": w.get("used_percent"), "resetsAt": reset})
    return out


def refresh_codex():
    for a in (x for x in _load()["accounts"] if x["provider"] == "codex"):
        tc, cwd, mtime = _codex_scan(a)
        if not tc:
            continue
        limits = _norm_codex_limits(tc.get("rate_limits"))
        if limits and (_usage.get(a["id"]) or {}).get("rateLimits") != limits:
            _usage[a["id"]] = {"rateLimits": limits, "updated": now_iso(), "source": "codex",
                               "plan": (tc.get("rate_limits") or {}).get("plan_type")}
            save_json(USAGE_FILE, _usage)
        info = tc.get("info") or {}
        for s in (v for v in _sessions.values() if v["account"] == a["id"] and v["started"] - 5 <= mtime):
            last, win = (info.get("last_token_usage") or {}).get("input_tokens"), info.get("model_context_window")
            if last and win:
                s["context"] = {"used": round(100 * last / win, 1), "size": win, "tokens": last}


def session_info(sid):
    s = _sessions.get(sid)
    if not s:
        return None
    return {k: v for k, v in s.items() if k != "secret"}


def all_sessions():
    return {sid: session_info(sid) for sid in list(_sessions)}


def forget(sid):
    _sessions.pop(sid, None)


def set_title(sid, title):
    if sid in _sessions:
        _sessions[sid]["title"] = title
