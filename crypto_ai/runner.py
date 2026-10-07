"""
runner.py -- runs ONE decision cycle. Scheduled every 6 hours; safe to run more often (idempotent).

ORDER OF A CYCLE (and why this order):
  1. verify the spec lock           -> no quiet goalpost moving
  2. cycle_id = UTC time floored to the 6h slot; already done? exit
  3. snapshot market data           -> one shared view of the world for ALL arms (fairness)
  4. per arm: stops -> breakers -> (liquidate if halted)   -> risk is handled before new ideas
  5. reference benchmarks rebalance (no risk engine)
  6. strategy toolbox signals (code) for every eligible coin
  7. each AI arm decides (LLM call, >= 65 s apart) -> slow; prices move while it thinks
  8. fetch FRESH quotes             -> fills happen at post-decision prices, never the ones the AI saw
  9. strategy arms + AI proposals -> risk engine -> paper exchange
 10. theses, equity, feedback, state -> saved atomically; everything appended to the journal

Failure policy: bad/missing market data => whole cycle skipped and logged (DATA_FAULT). Bad LLM
output => AI does nothing this cycle (AI_FAULT); baselines still run. Nothing is ever guessed.
If an asset is delisted every cycle becomes DATA_FAULT until an amendment handles it -- loud on
purpose (PREREGISTRATION.md section 8).

CLI:
  python -m crypto_ai.runner --state-dir crypto_ai_state_dryrun --dry-run      # mock LLM, no lock
  python -m crypto_ai.runner --state-dir crypto_ai_state                       # the real thing
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crypto_ai.agents.llm import LLMError, make_llm
from crypto_ai.agents.trader import apply_thesis_updates, decide
from crypto_ai.execution.paper_exchange import execute, replay_stops
from crypto_ai.journal import Journal, iso, now_utc, parse_iso
from crypto_ai.lock import load_config, verify_lock
from crypto_ai.market_data.coinbase import CoinbaseClient, DataFault
from crypto_ai.market_data.features import build_snapshot, fresh_quotes
from crypto_ai.portfolio.baselines import rebalance_direct, reference_targets
from crypto_ai.strategies import toolbox
from crypto_ai import universe as U
from crypto_ai.portfolio.state import Portfolio
from crypto_ai.risk.engine import evaluate, update_breakers

BANNER = "INTERIM -- INFORMATIONAL ONLY. Interim performance is not evidence of edge."


def cycle_id_for(now):
    return now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00Z")


def _alert(msg, dry_run):
    if dry_run:
        return
    try:
        from crypto_ai.notify import alert
        alert(msg)
    except Exception:
        pass                                   # alerts are best-effort, never block a cycle


def _load_arms(j, cfg):
    arms = {}
    for name in cfg["arms"]:
        d = j.load_json(f"arms/{name}.json")
        arms[name] = Portfolio.from_dict(d) if d else Portfolio(name, cfg["capital"]["initial_cash_usd"])
    return arms


def _execute_decisions(pf, decs, quotes, cfg, now, cycle_id, cause):
    fills = []
    for d in decs:
        if d["status"] not in ("APPROVED", "CLIPPED"):
            continue
        q = quotes.get(d["asset"])
        if q is None:
            d["status"], d["codes"] = "REJECTED", d["codes"] + ["R11_NO_FRESH_QUOTE"]
            continue
        f = execute(pf, d["asset"], d["side"], d["notional_usd"], q, cfg, now, cause, cycle_id,
                    stop_pct=d["stop_pct"], full_exit=d["full_exit"])
        if f:
            fills.append(f)
    return fills


def ai_arms(cfg):
    return [n for n, a in cfg["arms"].items() if a["kind"] == "ai"]


def ai_view(arm, ccfg, signals, pf):
    """Which coins this AI arm sees: the large tier, plus (for the large+mid arm) up to k mid
    coins the toolbox flags, plus anything it still holds (so it can always sell)."""
    spec = ccfg["arms"][arm]
    view = list(ccfg["large"])
    if spec["view"] == "large_mid":
        view += toolbox.mid_candidates(signals, ccfg["mid"], list(pf.positions), spec["max_mid_candidates"])
    view += [a for a in pf.positions if a not in view]
    return list(dict.fromkeys(view))


def scorecard(cfg, arms, mids):
    """What each strategy has actually done: its pre-run backtest AND its live paper record so far.
    This is how the AI 'learns from failure' honestly: from many trades' worth of evidence, shown
    to it as data, not from reacting to its own last loss."""
    init = cfg["capital"]["initial_cash_usd"]
    live = {}
    for name, spec in cfg["arms"].items():
        if spec["kind"] in ("strategy", "buy_hold", "equal_weight"):
            pf = arms[name]
            live[name] = {"return_pct": round(100 * (pf.equity(mids) / init - 1), 2),
                          "drawdown_pct": round(100 * pf.drawdown(mids), 2),
                          "fees_usd": round(pf.fees_usd, 2)}
    bt = {k: v for k, v in cfg["strategies"]["backtest_scorecard"].items() if not k.startswith("_")}
    return {"note": "backtest = before this run started (biased upward, see notes); live = this paper run so far "
                    "(short live records are mostly noise).", "backtest": bt, "live": live}


def ai_decide(j, arm, ccfg, llm, decision_id, snap, pf, signals, now, wake=None, card=None):
    """One AI arm's decision (no execution yet). Returns a context dict for ai_execute."""
    view = ai_view(arm, ccfg, signals, pf)
    vcfg = dict(ccfg, universe=view)
    snap_v = {"assets": {a: snap["assets"][a] for a in view}}
    theses = j.load_json(f"theses/{arm}.json", {})
    feedback = j.load_json(f"feedback/{arm}.json", {"note": "first cycle, no feedback yet"})
    extra = {"toolbox_signals": toolbox.signals_for_prompt(signals, view)}
    if card:
        extra["strategy_scorecard"] = card
    row = {"cycle_id": decision_id, "ts": iso(now), "arm": arm, "view": view,
           "scored_assets": list(ccfg["large"])}
    events, result = [], None
    try:
        result = decide(llm, vcfg, decision_id, snap_v, pf, theses, feedback, now, wake=wake,
                        extra=extra, arm=arm)
        last = result["attempts"][-1]
        row.update({"ok": result["ok"], "errors": result["errors"], "model_id": last["model_id"],
                    "provider": last.get("provider"),
                    "tokens_in": sum(a["tokens_in"] or 0 for a in result["attempts"]),
                    "tokens_out": sum(a["tokens_out"] or 0 for a in result["attempts"]),
                    "latency_s": last["latency_s"], "n_attempts": len(result["attempts"])})
        if not result["ok"]:
            events.append({"type": "AI_FAULT", "arm": arm, "errors": result["errors"]})
    except LLMError as e:
        row.update({"ok": False, "errors": [str(e)]})
        events.append({"type": "AI_FAULT", "arm": arm, "errors": [str(e)]})
    return {"arm": arm, "row": row, "result": result, "events": events, "theses": theses,
            "vcfg": vcfg, "snap_v": snap_v}


def ai_execute(j, ctx, pf, quotes, now, decision_id, cause, prompts_file):
    """Risk engine + fills + thesis updates for one AI arm. Returns (fills, decisions)."""
    arm, result, row = ctx["arm"], ctx["result"], ctx["row"]
    if result is not None:
        j.append(prompts_file, {"cycle_id": decision_id, "arm": arm, "system_sha256": result["system_sha256"],
                                "prompt_sha256": result["prompt_sha256"],
                                "user_prompt": result["user_prompt"], "attempts": result["attempts"]})
    decs, fills = [], []
    if result and result["ok"]:
        decs = evaluate(result["proposals"], pf, ctx["snap_v"], ctx["vcfg"], now)
        fills = _execute_decisions(pf, decs, quotes, ctx["vcfg"], now, decision_id, cause)
        theses, hist = apply_thesis_updates(ctx["theses"], result["parsed"], decision_id)
        for h in hist:
            j.append("theses_history.jsonl", {**h, "arm": arm, "source": cause})
        j.save_json(f"theses/{arm}.json", theses)
        p = result["parsed"]
        row.update({"outlook": p["outlook"], "decisions": p["decisions"],
                    "thesis_updates": p["thesis_updates"], "portfolio_note": p["portfolio_note"],
                    "fence_stripped": p["_fence_stripped"]})
    row["risk_decisions"] = decs
    return fills, decs


def save_feedback(j, arm, decision_id, decs, fills, events):
    j.save_json(f"feedback/{arm}.json", {
        "from": decision_id,
        "risk_engine": [{k: d[k] for k in ("asset", "action", "status", "codes", "requested_weight", "final_weight")}
                        for d in decs],
        "your_fills": [{k: f[k] for k in ("asset", "side", "qty", "price", "cause")} for f in fills if f["arm"] == arm],
        "events": [e for e in events if e.get("arm") in (None, arm)],
    })


def run_cycle(state_dir, cfg, client, llm, now=None, dry_run=False, require_lock=True):
    t0 = time.time()
    now = now or now_utc()
    j = Journal(state_dir)
    cid = cycle_id_for(now)

    if require_lock:
        ok, problems = verify_lock(state_dir)
        if not ok:
            j.append("events.jsonl", {"ts": iso(now), "cycle_id": cid, "type": "LOCK_MISMATCH",
                                      "problems": problems})
            _alert("LOCK MISMATCH -- refusing to run: " + "; ".join(problems), dry_run)
            return {"cycle_id": cid, "status": "LOCK_MISMATCH", "problems": problems}

    if any(r.get("cycle_id") == cid and r.get("status") != "DATA_FAULT" for r in j.read("cycles.jsonl")):
        return {"cycle_id": cid, "status": "ALREADY_DONE"}

    def data_fault(e):
        j.append("events.jsonl", {"ts": iso(now), "cycle_id": cid, "type": "DATA_FAULT", "error": str(e)})
        j.append("cycles.jsonl", {"cycle_id": cid, "started_at": iso(now), "status": "DATA_FAULT",
                                  "error": str(e), "dry_run": dry_run})
        return {"cycle_id": cid, "status": "DATA_FAULT", "error": str(e)}

    # ---- 3. universe + snapshot ------------------------------------------------------------------
    arms = _load_arms(j, cfg)
    events = []
    try:
        uni, uev = U.current(j, cfg, client, now)
    except DataFault as e:
        return data_fault(f"universe: {e}")
    if uev:
        events.append(uev)
    held = {a for pf in arms.values() for a in pf.positions}
    ccfg = U.cycle_config(cfg, uni, held)
    try:
        snap, hourly = build_snapshot(ccfg, client, now)
    except DataFault as e:
        return data_fault(e)
    j.append("snapshots.jsonl", {"cycle_id": cid, "ts": iso(now), "assets": snap["assets"],
                                 "large": ccfg["large"], "mid": ccfg["mid"]})
    mids = {a: v["mid"] for a, v in snap["assets"].items()}
    snap_quotes = {a: {"mid": v["mid"], "bid": v["bid"], "ask": v["ask"],
                       "volume_24h_usd": v["volume_24h_usd"]} for a, v in snap["assets"].items()}
    fills = []

    # ---- 4. stops and breakers (constrained arms only) ----------------------------------------
    for name, pf in arms.items():
        if not cfg["arms"][name]["constrained"]:
            continue
        since = parse_iso(pf.last_ts).timestamp() if pf.last_ts else None
        for f in replay_stops(pf, hourly, snap["assets"], ccfg, now, cid, since_ts=since):
            fills.append(f)
            events.append({"type": "STOP_TRIGGERED", "arm": name, "asset": f["asset"],
                           "price": f["price"], "stop_price": f["stop_price"]})
        liquidate, evs = update_breakers(pf, mids, now, cfg)
        events += evs
        if liquidate:
            for a in list(pf.positions):
                f = execute(pf, a, "sell", 0, snap_quotes[a], ccfg, now, "breaker", cid, full_exit=True)
                if f:
                    fills.append(f)
            _alert(f"{name}: drawdown halt, liquidated, buys locked until {pf.halted_until}", dry_run)

    # ---- 5. reference benchmarks --------------------------------------------------------------
    for name, pf in arms.items():
        if cfg["arms"][name]["kind"] in ("buy_hold", "equal_weight"):
            targets = reference_targets(name, pf, ccfg, now)
            if targets:
                fills += rebalance_direct(pf, targets, snap_quotes, ccfg, now, cid)

    # ---- 6. strategy toolbox signals ----------------------------------------------------------
    signals = toolbox.compute_signals(snap["daily"], ccfg["eligible"], ccfg)
    j.append("signals.jsonl", {"cycle_id": cid, "ts": iso(now), "signals": signals})

    # ---- 7. AI arms decide (sequential; the LLM client spaces calls for the token-per-minute cap)
    card = scorecard(cfg, arms, mids)
    ctxs = [ai_decide(j, arm, ccfg, llm, cid, snap, arms[arm], signals, now, card=card) for arm in ai_arms(cfg)]
    for c in ctxs:
        events += c["events"]

    # ---- 8. fresh quotes, then 9. constrained execution -----------------------------------------
    quotes = fresh_quotes(ccfg, client, ccfg["universe"], now_utc() if not dry_run else now)
    strat_decs = {}
    for name, spec in cfg["arms"].items():
        if spec["kind"] != "strategy":
            continue
        pf = arms[name]
        props = toolbox.strategy_proposals(name, spec["strategy"], pf, signals, snap, ccfg, now)
        decs = evaluate(props, pf, snap, ccfg, now)
        fills += _execute_decisions(pf, decs, quotes, ccfg, now, cid, "strategy")
        strat_decs[name] = decs
        j.append("decisions.jsonl", {"cycle_id": cid, "ts": iso(now), "arm": name, "risk_decisions": decs})
    ai_rows = []
    for c in ctxs:
        f, decs = ai_execute(j, c, arms[c["arm"]], quotes, now, cid, "ai", "prompts.jsonl")
        fills += f
        j.append("decisions.jsonl", c["row"])
        ai_rows.append(c["row"])
        save_feedback(j, c["arm"], cid, decs, fills, events)

    # ---- 10. persist ----------------------------------------------------------------------------
    for f in fills:
        j.append("orders.jsonl", f)
    for e in events:
        j.append("events.jsonl", {"ts": iso(now), "cycle_id": cid, **e})
    for name, pf in arms.items():
        eq = pf.equity(mids)
        j.append("equity.jsonl", {"cycle_id": cid, "ts": iso(now), "arm": name, "equity": eq,
                                  "cash": pf.cash, "gross_exposure": 1 - pf.cash / eq if eq > 0 else 0,
                                  "drawdown": pf.drawdown(mids), "peak": pf.peak_equity,
                                  "fees_usd": pf.fees_usd, "spread_usd": pf.spread_usd,
                                  "slippage_usd": pf.slippage_usd, "traded_usd": pf.traded_notional_usd,
                                  "n_positions": len(pf.positions)})
        pf.last_ts = iso(now)
        j.save_json(f"arms/{name}.json", pf.to_dict())
    all_ok = all(r.get("ok") for r in ai_rows)
    status = "OK" if all_ok else "OK_AI_FAULT"
    j.append("cycles.jsonl", {"cycle_id": cid, "started_at": iso(now), "finished_at": iso(now_utc()),
                              "duration_s": round(time.time() - t0, 1), "status": status,
                              "ai": {r["arm"]: {"ok": r.get("ok"), "model_id": r.get("model_id"),
                                                "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out")}
                                     for r in ai_rows},
                              "tokens_in": sum(r.get("tokens_in") or 0 for r in ai_rows),
                              "tokens_out": sum(r.get("tokens_out") or 0 for r in ai_rows),
                              "model_id": next((r.get("model_id") for r in ai_rows if r.get("model_id")), None),
                              "universe_month": uni["asof_month"], "n_eligible": len(ccfg["eligible"]),
                              "n_fills": len(fills), "n_events": len(events), "dry_run": dry_run})
    return {"cycle_id": cid, "status": status, "fills": len(fills), "events": events,
            "ai_errors": {r["arm"]: r.get("errors") for r in ai_rows}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--dry-run", action="store_true", help="mock LLM, no lock required, no alerts")
    ap.add_argument("--smoke", action="store_true",
                    help="REAL LLM, no lock required. Pre-lock plumbing test only: must use a throwaway "
                         "state dir, never the experiment's. Results are not part of the experiment.")
    a = ap.parse_args()
    if a.smoke and os.path.exists(os.path.join(a.state_dir, "lock.json")):
        sys.exit("--smoke refuses to write into a locked experiment state dir")
    cfg = load_config()
    llm = make_llm(cfg, "mock" if a.dry_run else None)
    out = run_cycle(a.state_dir, cfg, CoinbaseClient(), llm, dry_run=a.dry_run,
                    require_lock=not (a.dry_run or a.smoke))
    print(BANNER)
    print({k: v for k, v in out.items() if k != "events"})
    for e in out.get("events", []) or []:
        print("  event:", e)
    sys.exit(0 if out["status"] in ("OK", "OK_AI_FAULT", "ALREADY_DONE") else 1)
