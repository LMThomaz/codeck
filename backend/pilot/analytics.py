"""Análise: PRs concluídas (cache de 15 min), indicadores, por criador/repositório/destino e idade das abertas."""
import statistics
import time
from datetime import timedelta

from .core import ctx, lock, now, now_iso, parse_dt, read_activity, state

analytics_cache = {}  # org -> {"at": ts, "days": n, "prs": [...]}


def hours_between(a, b):
    a, b = parse_dt(a), parse_dt(b)
    return (b - a).total_seconds() / 3600 if a and b else None


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def completed_prs(days, force=False):
    out, errors = [], {}
    for org in list(ctx.orgs.values()):
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
    my_names = {o.me["name"].lower() for o in ctx.orgs.values() if o.me} | {o.me["id"] for o in ctx.orgs.values() if o.me}
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


