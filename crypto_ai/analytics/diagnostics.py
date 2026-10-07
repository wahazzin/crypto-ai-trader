"""
diagnostics.py -- three honesty checks on the AI (roadmap phase 14, promised in PREREGISTRATION).

1. RANDOM POLICIES ("is it better than luck?")
   Replays the AI's scheduled decisions through a simple replay engine, and N random "monkeys"
   through the SAME engine, risk rules and costs. Each monkey is calibrated ONLY on the AI's
   behaviour (how often it trades, how many coins per decision, what sizes it asks for), never
   on returns. If the AI isn't above most monkeys, its picks added nothing beyond its trading style.
   The replay uses cycle snapshots (6-hourly) and modelled fills, so it's an approximation of the
   live engine; that's fine because AI and monkeys get exactly the same approximation.

2. WAKE-UPS VS SCHEDULED: did the between-cycle wake-ups help or hurt?
   (a) closed round trips split by what opened them (scheduled cycle vs wake-up),
   (b) actual live equity vs the scheduled-only replay from (1).

3. CONFIDENCE CALIBRATION (project rule 11): are high-confidence buys actually better?
   For every BUY/ADD: the coin's next-24h and next-72h return, grouped by stated confidence.
   Also the outlook ladder: average next-24h return for each outlook score -2..+2.

Everything is labelled with its sample size. Small samples are noise; the verdict only comes
from the pre-registered test at the decision point.
"""
import random
from datetime import timedelta

from crypto_ai import universe as U
from crypto_ai.analytics.weekly import closed_trades
from crypto_ai.execution.paper_exchange import execute
from crypto_ai.journal import parse_iso
from crypto_ai.portfolio.state import Portfolio
from crypto_ai.risk.engine import Proposal, evaluate, update_breakers

TRADE_ACTIONS = ("BUY", "ADD", "REDUCE", "SELL", "EXIT")


def _t(cid):
    return parse_iso(cid.replace("Z", ":00Z")) if len(cid) == 17 else parse_iso(cid)


def replay(cfg, snaps, proposals_by_cycle, arm="replay"):
    """Simple engine: each cycle -> stops on the cycle mid -> breakers -> risk engine -> fills at
    snapshot bid/ask + modelled slippage. Returns {cycle_id: equity}."""
    pf = Portfolio(arm, cfg["capital"]["initial_cash_usd"])
    eq = {}
    for s in snaps:
        cid, now = s["cycle_id"], _t(s["cycle_id"])
        assets = s["assets"]
        mids = {a: v["mid"] for a, v in assets.items()}
        ccfg = U.cycle_config(cfg, {"large": s.get("large", []), "mid": s.get("mid", [])}, set(pf.positions))
        q = {a: {"mid": v["mid"], "bid": v["bid"], "ask": v["ask"], "volume_24h_usd": v["volume_24h_usd"]}
             for a, v in assets.items()}
        for a in list(pf.positions):
            if a in mids and mids[a] <= pf.positions[a].stop_price:
                execute(pf, a, "sell", 0, q[a], ccfg, now, "stop", cid, full_exit=True)
        liquidate, _ = update_breakers(pf, mids, now, cfg)
        if liquidate:
            for a in list(pf.positions):
                if a in q:
                    execute(pf, a, "sell", 0, q[a], ccfg, now, "breaker", cid, full_exit=True)
        props = proposals_by_cycle(cid, pf, s) or []
        for d in evaluate(props, pf, {"assets": assets}, ccfg, now):
            if d["status"] in ("APPROVED", "CLIPPED") and d["asset"] in q:
                execute(pf, d["asset"], d["side"], d["notional_usd"], q[d["asset"]], ccfg, now, "replay", cid,
                        stop_pct=d.get("stop_pct"), full_exit=d.get("full_exit", False))
        eq[cid] = pf.equity({a: mids[a] for a in mids})
    return eq


def behaviour(rows):
    """What the AI's trading looks like (no returns involved)."""
    active = [r for r in rows if any(d["action"] in TRADE_ACTIONS for d in r.get("decisions", []))]
    n_act = [sum(d["action"] in TRADE_ACTIONS for d in r["decisions"]) for r in active]
    tws = [d["target_weight"] for r in active for d in r["decisions"]
           if d["action"] in ("BUY", "ADD") and d.get("target_weight")]
    return {"p_act": len(active) / len(rows) if rows else 0.0, "n_act": n_act or [1], "tws": tws or [0.1]}


def monkey(beh, views, seed):
    rng = random.Random(seed)

    def props(cid, pf, snap):
        if rng.random() >= beh["p_act"]:
            return []
        view = [a for a in views.get(cid, []) if a in snap["assets"]]
        if not view:
            return []
        out = []
        for a in rng.sample(view, min(rng.choice(beh["n_act"]), len(view))):
            if a in pf.positions:
                act = rng.choice(("ADD", "REDUCE", "EXIT"))
                if act == "EXIT":
                    out.append(Proposal("m", a, "EXIT", None, None, "m"))
                else:
                    w = pf.weights({k: v["mid"] for k, v in snap["assets"].items()}).get(a, 0.0)
                    tw = w + rng.choice(beh["tws"]) / 2 if act == "ADD" else w / 2
                    out.append(Proposal("m", a, act, min(tw, 1.0), None, "m"))
            else:
                out.append(Proposal("m", a, "BUY", rng.choice(beh["tws"]), None, "m"))
        return out
    return props


def _ret(eq):
    v = list(eq.values())
    return v[-1] / v[0] - 1 if len(v) > 1 and v[0] > 0 else 0.0


def random_policy_test(cfg, snaps, ai_rows, n=200, seed=7):
    rows = {r["cycle_id"]: r for r in ai_rows}
    snaps = [s for s in snaps if s["cycle_id"] in rows]
    if len(snaps) < 2:
        return {"n_cycles": len(snaps), "note": "not enough cycles yet"}
    beh = behaviour(list(rows.values()))
    views = {cid: r.get("view", []) for cid, r in rows.items()}

    def ai_props(cid, pf, snap):
        return [Proposal("ai", d["asset"], d["action"], d.get("target_weight"), d.get("stop_loss_pct"), "ai")
                for d in rows[cid].get("decisions", [])]
    ai_eq = replay(cfg, snaps, ai_props)
    init = cfg["capital"]["initial_cash_usd"]
    ai_r = list(ai_eq.values())[-1] / init - 1
    rand = sorted(list(replay(cfg, snaps, monkey(beh, views, seed + i)).values())[-1] / init - 1 for i in range(n))
    pct = sum(r < ai_r for r in rand) / n
    return {"n_cycles": len(snaps), "n_policies": n, "ai_replay_return": ai_r, "percentile": pct,
            "random_median": rand[n // 2], "random_p5": rand[int(0.05 * n)], "random_p95": rand[int(0.95 * n) - 1],
            "behaviour": {"p_act": beh["p_act"], "avg_coins_per_active_cycle": sum(beh["n_act"]) / len(beh["n_act"]),
                          "avg_target_weight": sum(beh["tws"]) / len(beh["tws"])},
            "ai_replay_equity": ai_eq}


def fwd_return(mids_by_cycle, cid, asset, hours):
    c1 = (_t(cid) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:00Z")
    m0, m1 = mids_by_cycle.get(cid, {}), mids_by_cycle.get(c1, {})
    if asset in m0 and asset in m1 and m0[asset] > 0:
        return m1[asset] / m0[asset] - 1
    return None


def calibration(ai_rows, snaps):
    mids = {s["cycle_id"]: {a: v["mid"] for a, v in s["assets"].items()} for s in snaps}
    buckets = {"<60": [], "60-69": [], "70-79": [], "80+": []}
    for r in ai_rows:
        for d in r.get("decisions", []):
            if d["action"] not in ("BUY", "ADD") or d.get("confidence") is None:
                continue
            c = d["confidence"]
            k = "<60" if c < 60 else "60-69" if c < 70 else "70-79" if c < 80 else "80+"
            buckets[k].append((fwd_return(mids, r["cycle_id"], d["asset"], 24), fwd_return(mids, r["cycle_id"], d["asset"], 72)))
    out = {}
    for k, v in buckets.items():
        r24 = [x for x, _ in v if x is not None]
        r72 = [y for _, y in v if y is not None]
        out[k] = {"n": len(v), "n_scored_72h": len(r72),
                  "avg_24h": sum(r24) / len(r24) if r24 else None,
                  "avg_72h": sum(r72) / len(r72) if r72 else None,
                  "hit_72h": sum(y > 0 for y in r72) / len(r72) if r72 else None}
    ladder = {s: [] for s in (-2, -1, 0, 1, 2)}
    for r in ai_rows:
        scored = set(r.get("scored_assets") or [])
        for a, s in (r.get("outlook") or {}).items():
            if a in scored:
                f = fwd_return(mids, r["cycle_id"], a, 24)
                if f is not None:
                    ladder[s].append(f)
    return out, {s: (len(v), sum(v) / len(v) if v else None) for s, v in ladder.items()}


def wakeup_split(orders, arm):
    trades = [t for t in closed_trades(orders) if t["arm"] == arm]
    opened_by = {}
    for o in orders:
        if o["arm"] == arm and o["side"] == "buy":
            opened_by[(o["asset"], o["ts"])] = o["cause"]
    out = {"scheduled": [], "wake-up": []}
    for t in trades:
        cause = opened_by.get((t["asset"], t["open_ts"]), "ai")
        out["wake-up" if cause == "ai_event" else "scheduled"].append(t["pnl_usd"])
    return {k: {"closed": len(v), "pnl_usd": sum(v)} for k, v in out.items()}


def _p(x):
    return "—" if x is None else f"{100 * x:+.2f}%"


def markdown(cfg, j, n_random=200):
    snaps, dec, orders = j.read("snapshots.jsonl"), j.read("decisions.jsonl"), j.read("orders.jsonl")
    eq = j.read("equity.jsonl")
    lines = ["## Honesty checks (phase 14) — small samples are noise", ""]
    for arm in cfg["evaluation"].get("scored_ai_arms", []):
        rows = [r for r in dec if r.get("arm") == arm and r.get("ok") and "view" in r]
        rp = random_policy_test(cfg, snaps, rows, n_random)
        lines += [f"### `{arm}`", ""]
        if "percentile" in rp:
            b = rp["behaviour"]
            lines += [f"**Better than luck?** AI replay {_p(rp['ai_replay_return'])} vs {rp['n_policies']} random policies "
                      f"(median {_p(rp['random_median'])}, 5–95%: {_p(rp['random_p5'])} … {_p(rp['random_p95'])}). "
                      f"AI beats **{100 * rp['percentile']:.0f}%** of them over {rp['n_cycles']} cycles. "
                      f"(Monkeys copy its style: trades in {100 * b['p_act']:.0f}% of cycles, "
                      f"~{b['avg_coins_per_active_cycle']:.1f} coins, ~{100 * b['avg_target_weight']:.0f}% size.)", ""]
            live = [r for r in eq if r["arm"] == arm]
            if live:
                live_r = live[-1]["equity"] / cfg["capital"]["initial_cash_usd"] - 1
                lines += [f"**Wake-ups worth it?** Live (with wake-ups) {_p(live_r)} vs scheduled-only replay "
                          f"{_p(rp['ai_replay_return'])} (approximate: different fill engines).", ""]
        else:
            lines += [f"Random-policy test: {rp.get('note')} ({rp['n_cycles']} cycles).", ""]
        ws = wakeup_split(orders, arm)
        lines += [f"Closed trades opened at a scheduled cycle: {ws['scheduled']['closed']} (P&L ${ws['scheduled']['pnl_usd']:+,.2f}); "
                  f"opened by a wake-up: {ws['wake-up']['closed']} (P&L ${ws['wake-up']['pnl_usd']:+,.2f}).", ""]
        cal, ladder = calibration(rows, snaps)
        lines += ["**Confidence vs outcome (rule 11)** — buys grouped by the AI's stated confidence:", "",
                  "| Confidence | Buys | Scored (72h) | Avg next 24h | Avg next 72h | Up after 72h |", "|---|---|---|---|---|---|"]
        for k, v in cal.items():
            hit = "—" if v["hit_72h"] is None else f"{100 * v['hit_72h']:.0f}%"
            lines.append(f"| {k} | {v['n']} | {v['n_scored_72h']} | {_p(v['avg_24h'])} | {_p(v['avg_72h'])} | {hit} |")
        lines += ["", "**Outlook ladder** (large tier): average next-24h return by the AI's outlook score. "
                  "Skill looks like a staircase going up from −2 to +2.", "",
                  "| Outlook | −2 | −1 | 0 | +1 | +2 |", "|---|---|---|---|---|---|",
                  "| n | " + " | ".join(str(ladder[s][0]) for s in (-2, -1, 0, 1, 2)) + " |",
                  "| avg next 24h | " + " | ".join(_p(ladder[s][1]) for s in (-2, -1, 0, 1, 2)) + " |", ""]
    return "\n".join(lines)
