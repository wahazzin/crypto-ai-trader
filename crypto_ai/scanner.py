"""
scanner.py -- the bot's eyes between AI cycles. Runs every 5 minutes on GitHub Actions.

WHAT IT DOES, IN ORDER
  1. Lock check. No lock, no work (and nothing is written, so a 5-minute schedule can't spam logs).
  2. If a scheduled 6-hour cycle is due, run it (runner.run_cycle) and stop. One entry point for
     both jobs means two runs can never write the state at the same time.
  3. Otherwise SCAN with plain code -- free, no AI:
       a. hard stops on 5-minute candles, for both constrained arms (ai_pv and trend_quant alike)
       b. circuit breakers (daily loss, drawdown)
       c. triggers for the AI: its own exit_below / review_above crossed on a held coin, a big
          1h move, or a volume spike with a real move behind it
  4. If a trigger fires AND the budget allows, wake the AI once with the reasons ("wake"), send its
     answer through the same risk engine, and fill on fresh quotes.

WHY THE AI ISN'T SIMPLY CALLED EVERY 5 MINUTES
  The free model has a budget (~200k tokens/day, ~5.6k per call => ~35 calls/day), and every trade
  costs >=0.8% round trip. Looking is free; asking and trading are not. See ROADMAP.md section 3.

WHAT IS AND ISN'T PART OF THE SCORED TEST
  Wake-up decisions go to event_decisions.jsonl / event_prompts.jsonl, never cycles.jsonl or
  decisions.jsonl, so the pre-registered IC test (scheduled outlooks only) is untouched. Their
  trades DO count in the AI portfolio's P&L.

QUIET SCANS WRITE NOTHING
  If nothing happened, no file changes, so the workflow makes no commit. A heartbeat is written
  once per `heartbeat_minutes` so we can see the scanner is alive.

Usage:
  python -m crypto_ai.scanner --state-dir DIR            # real (needs the lock)
  python -m crypto_ai.scanner --state-dir DIR --smoke    # real AI, no lock, throwaway dir only
"""
import argparse
import os
import sys
import time
from datetime import timedelta

from crypto_ai.agents.llm import LLMError, make_llm
from crypto_ai.agents.trader import apply_thesis_updates, decide
from crypto_ai.execution.paper_exchange import execute, replay_stops
from crypto_ai.journal import Journal, iso, now_utc, parse_iso
from crypto_ai.lock import load_config, verify_lock
from crypto_ai.market_data.coinbase import CoinbaseClient, DataFault, closed_only
from crypto_ai.market_data.features import build_snapshot, fresh_quotes
from crypto_ai.risk.engine import evaluate, update_breakers
from crypto_ai.runner import _alert, _execute_decisions, _load_arms, cycle_id_for, run_cycle


def _slot_start(now):
    return parse_iso(cycle_id_for(now).replace("Z", ":00Z"))


def cycle_due(j, cfg, now):
    """A scheduled cycle is due if this 6h slot has no successful cycle yet and the grace period
    (for the last hourly candle to close) has passed."""
    cid = cycle_id_for(now)
    if now < _slot_start(now) + timedelta(minutes=cfg["scanner"]["cycle_grace_minutes"]):
        return False
    return not any(r.get("cycle_id") == cid and r.get("status") != "DATA_FAULT" for r in j.read("cycles.jsonl"))


def _market(cfg, client, now):
    """Live quotes + closed 5-minute candles for the whole universe. Raises DataFault."""
    g = cfg["scanner"]["candle_granularity_s"]
    now_ts = int(now.timestamp())
    quotes, candles = {}, {}
    for p in cfg["universe"]:
        tk = client.ticker(p)
        age = (now - tk["time"]).total_seconds()
        if abs(age) > cfg["data"]["max_quote_age_seconds"] or not (0 < tk["bid"] <= tk["ask"]):
            raise DataFault(f"{p}: stale or invalid quote")
        mid = (tk["bid"] + tk["ask"]) / 2
        quotes[p] = {"mid": mid, "bid": tk["bid"], "ask": tk["ask"],
                     "spread_bps": (tk["ask"] - tk["bid"]) / mid * 1e4,
                     "volume_24h_usd": tk["volume_base"] * mid}
        candles[p] = closed_only(client.candles(p, g), g, now_ts)
    return quotes, candles


def find_triggers(cfg, quotes, candles, ai_pf, theses):
    """Pure function: what (if anything) is worth waking the AI for. Returns a list of dicts,
    each with a dedupe `key`."""
    sc, tr = cfg["scanner"], cfg["scanner"]["triggers"]
    per_hour = 3600 // sc["candle_granularity_s"]
    out = []
    for a, q in quotes.items():
        mid, t = q["mid"], (theses or {}).get(a, {})
        held = a in ai_pf.positions
        if held and tr["exit_below"] and t.get("exit_below") and mid < t["exit_below"]:
            out.append({"key": f"{a}:exit_below:{t['exit_below']}", "asset": a, "type": "EXIT_BELOW_CROSSED",
                        "price": mid, "level": t["exit_below"], "once": True})
        if held and tr["review_above"] and t.get("review_above") and mid >= t["review_above"]:
            out.append({"key": f"{a}:review_above:{t['review_above']}", "asset": a, "type": "REVIEW_ABOVE_REACHED",
                        "price": mid, "level": t["review_above"], "once": True})
        c = candles.get(a, [])
        if len(c) < per_hour:
            continue
        move = mid / c[-per_hour]["open"] - 1
        if abs(move) * 100 >= tr["move_1h_pct"]:
            out.append({"key": f"{a}:move", "asset": a, "type": "BIG_MOVE_1H", "price": mid,
                        "move_1h_pct": round(100 * move, 2), "once": False})
        if len(c) >= per_hour * 25:
            last = sum(x["volume"] for x in c[-per_hour:])
            prev = c[-per_hour * 25:-per_hour]
            hours = sorted(sum(x["volume"] for x in prev[i:i + per_hour]) for i in range(0, len(prev), per_hour))
            med = hours[len(hours) // 2]
            if med > 0 and last / med >= tr["volume_spike_ratio"] and abs(move) * 100 >= tr["volume_spike_min_move_pct"]:
                out.append({"key": f"{a}:volume", "asset": a, "type": "VOLUME_SPIKE", "price": mid,
                            "volume_ratio": round(last / med, 2), "move_1h_pct": round(100 * move, 2),
                            "once": False})
    return out


def _new_triggers(triggers, st, now, cfg):
    """Drop triggers already handled: `once` triggers never refire for the same level; the others
    have a cooldown."""
    cool = timedelta(minutes=cfg["scanner"]["cooldown_minutes"])
    fresh = []
    for t in triggers:
        last = st["fired"].get(t["key"])
        if last is None or (not t["once"] and now - parse_iso(last) >= cool):
            fresh.append(t)
    return fresh


def _budget_block(st, now, cfg):
    """Returns a reason string if the AI may not be woken now, else None."""
    sc = cfg["scanner"]
    day = now.strftime("%Y-%m-%d")
    if st["calls_day"] == day and st["calls_today"] >= sc["max_event_calls_per_day"]:
        return "DAILY_CAP"
    if st.get("last_call") and now - parse_iso(st["last_call"]) < timedelta(minutes=sc["min_minutes_between_event_calls"]):
        return "SPACING"
    next_slot = _slot_start(now) + timedelta(hours=6)
    if next_slot - now < timedelta(minutes=sc["quiet_minutes_before_cycle"]):
        return "CYCLE_SOON"
    return None


def run_scan(state_dir, cfg, client, llm, now=None, dry_run=False, require_lock=True):
    t0 = time.time()
    now = now or now_utc()
    j = Journal(state_dir)

    if require_lock:
        ok, problems = verify_lock(state_dir)
        if not ok:
            return {"mode": "none", "status": "LOCK_MISMATCH", "problems": problems}

    if cycle_due(j, cfg, now):
        out = run_cycle(state_dir, cfg, client, llm, now, dry_run=dry_run, require_lock=require_lock)
        return {"mode": "cycle", **out}

    st = j.load_json("scanner_state.json", {"fired": {}, "calls_day": None, "calls_today": 0,
                                             "last_call": None, "last_heartbeat": None, "scans_since_heartbeat": 0})
    sid = f"{now:%Y-%m-%dT%H:%MZ}"
    scan_id = f"scan:{sid}"

    try:
        quotes, candles = _market(cfg, client, now)
    except DataFault as e:
        st["scans_since_heartbeat"] += 1
        st["last_data_fault"] = {"ts": iso(now), "error": str(e)}
        j.save_json("scanner_state.json", st)
        return {"mode": "scan", "status": "DATA_FAULT", "error": str(e)}

    mids = {a: q["mid"] for a, q in quotes.items()}
    arms = _load_arms(j, cfg)
    fills, events = [], []

    # ---- a/b. stops and breakers, every constrained arm alike ------------------------------------
    for name, pf in arms.items():
        if not cfg["arms"][name]["constrained"]:
            continue
        since = parse_iso(pf.last_ts).timestamp() if pf.last_ts else None
        for f in replay_stops(pf, candles, quotes, cfg, now, scan_id, since_ts=since,
                              granularity=cfg["scanner"]["candle_granularity_s"]):
            fills.append(f)
            events.append({"type": "STOP_TRIGGERED", "arm": name, "asset": f["asset"],
                           "price": f["price"], "stop_price": f["stop_price"], "source": "scanner"})
        liquidate, evs = update_breakers(pf, mids, now, cfg)
        events += [{**e, "source": "scanner"} for e in evs]
        if liquidate:
            for a in list(pf.positions):
                f = execute(pf, a, "sell", 0, quotes[a], cfg, now, "breaker", scan_id, full_exit=True)
                if f:
                    fills.append(f)
            _alert(f"{name}: drawdown halt (scanner), liquidated, buys locked until {pf.halted_until}", dry_run)

    # ---- c. triggers -------------------------------------------------------------------------------
    ai = arms["ai_pv"]
    theses = j.load_json("theses.json", {})
    trig = _new_triggers(find_triggers(cfg, quotes, candles, ai, theses), st, now, cfg)
    woke = None
    if trig:
        block = _budget_block(st, now, cfg)
        if ai.halted_until:
            block = "ARM_HALTED"
        events.append({"type": "SCANNER_TRIGGER", "triggers": [{k: v for k, v in t.items() if k != "once"} for t in trig],
                       "woke_ai": block is None, "blocked_by": block})
        if block is None:
            woke = _wake_ai(j, cfg, client, llm, now, sid, ai, theses, trig, dry_run)
            fills += woke["fills"]
            events += woke["events"]
            day = now.strftime("%Y-%m-%d")
            st["calls_today"] = st["calls_today"] + 1 if st["calls_day"] == day else 1
            st["calls_day"], st["last_call"] = day, iso(now)
            for t in trig:
                st["fired"][t["key"]] = iso(now)

    # ---- persist (only if something happened, or heartbeat due) ---------------------------------
    st["scans_since_heartbeat"] += 1
    hb_due = (st.get("last_heartbeat") is None or
              now - parse_iso(st["last_heartbeat"]) >= timedelta(minutes=cfg["scanner"]["heartbeat_minutes"]))
    if not (fills or events or hb_due):
        return {"mode": "scan", "status": "QUIET", "duration_s": round(time.time() - t0, 1)}

    for f in fills:
        j.append("orders.jsonl", f)
    for e in events:
        j.append("events.jsonl", {"ts": iso(now), "cycle_id": scan_id, **e})
    for name, pf in arms.items():
        pf.last_ts = iso(now)
        j.save_json(f"arms/{name}.json", pf.to_dict())
    if hb_due:
        st["last_heartbeat"] = iso(now)
        st["heartbeat"] = {"ts": iso(now), "scans": st["scans_since_heartbeat"],
                           "equity": {n: round(p.equity(mids), 2) for n, p in arms.items()}}
        st["scans_since_heartbeat"] = 0
    st["fired"] = {k: v for k, v in st["fired"].items() if now - parse_iso(v) < timedelta(days=30)}
    j.save_json("scanner_state.json", st)
    return {"mode": "scan", "status": "ACTIVE" if (fills or events) else "HEARTBEAT",
            "fills": len(fills), "events": events, "woke_ai": woke is not None,
            "duration_s": round(time.time() - t0, 1)}


def _wake_ai(j, cfg, client, llm, now, sid, ai, theses, triggers, dry_run):
    """One event-driven AI decision. Same validation, same risk engine, same fills as a cycle."""
    eid = f"{sid}-event"
    wake = {"reason": [{k: v for k, v in t.items() if k not in ("once", "key")} for t in triggers],
            "note": "Woken between scheduled cycles by the code scanner. Act only if this matters. "
                    "DO_NOTHING is fine. Outlook required but not scored."}
    row = {"event_id": eid, "ts": iso(now), "arm": "ai_pv", "wake": wake}
    fills, events, decs = [], [], []
    try:
        snap, _ = build_snapshot(cfg, client, now)
    except DataFault as e:
        row.update({"ok": False, "errors": [f"snapshot: {e}"]})
        j.append("event_decisions.jsonl", row)
        return {"fills": [], "events": [{"type": "EVENT_DATA_FAULT", "error": str(e)}]}
    feedback = j.load_json("ai_feedback.json", {"note": "no feedback yet"})
    try:
        result = decide(llm, cfg, eid, snap, ai, theses, feedback, now, wake=wake)
        last = result["attempts"][-1]
        j.append("event_prompts.jsonl", {"event_id": eid, "system_sha256": result["system_sha256"],
                                         "prompt_sha256": result["prompt_sha256"],
                                         "user_prompt": result["user_prompt"], "attempts": result["attempts"]})
        row.update({"ok": result["ok"], "errors": result["errors"], "model_id": last["model_id"],
                    "tokens_in": sum(a["tokens_in"] or 0 for a in result["attempts"]),
                    "tokens_out": sum(a["tokens_out"] or 0 for a in result["attempts"]),
                    "latency_s": last["latency_s"], "n_attempts": len(result["attempts"])})
        if result["ok"]:
            quotes = fresh_quotes(cfg, client, cfg["universe"], now_utc() if not dry_run else now)
            decs = evaluate(result["proposals"], ai, snap, cfg, now)
            fills = _execute_decisions(ai, decs, quotes, cfg, now, eid, "ai_event")
            new_theses, hist = apply_thesis_updates(theses, result["parsed"], eid)
            for h in hist:
                j.append("theses_history.jsonl", {**h, "source": "event"})
            j.save_json("theses.json", new_theses)
            p = result["parsed"]
            row.update({"outlook": p["outlook"], "decisions": p["decisions"],
                        "thesis_updates": p["thesis_updates"], "portfolio_note": p["portfolio_note"]})
        else:
            events.append({"type": "AI_FAULT", "errors": result["errors"], "source": "event"})
    except LLMError as e:
        row.update({"ok": False, "errors": [str(e)]})
        events.append({"type": "AI_FAULT", "errors": [str(e)], "source": "event"})
    row["risk_decisions"] = decs
    j.append("event_decisions.jsonl", row)
    if decs or fills:
        j.save_json("ai_feedback.json", {
            "from_event": eid,
            "risk_engine": [{k: d[k] for k in ("asset", "action", "status", "codes", "requested_weight", "final_weight")}
                            for d in decs],
            "your_fills": [{k: f[k] for k in ("asset", "side", "qty", "price", "cause")} for f in fills],
            "events": []})
    return {"fills": fills, "events": events}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--dry-run", action="store_true", help="mock LLM, no lock, no alerts")
    ap.add_argument("--smoke", action="store_true", help="REAL LLM, no lock. Throwaway state dir only.")
    a = ap.parse_args()
    if a.smoke and os.path.exists(os.path.join(a.state_dir, "lock.json")):
        sys.exit("--smoke refuses to write into a locked experiment state dir")
    cfg = load_config()
    llm = make_llm(cfg, "mock" if a.dry_run else None)
    out = run_scan(a.state_dir, cfg, CoinbaseClient(), llm, dry_run=a.dry_run,
                   require_lock=not (a.dry_run or a.smoke))
    print({k: v for k, v in out.items() if k != "events"})
    for e in out.get("events", []) or []:
        print("  event:", e)
    ok = out["status"] in ("OK", "OK_AI_FAULT", "ALREADY_DONE", "QUIET", "HEARTBEAT", "ACTIVE") \
        or (out.get("mode") == "scan" and out["status"] == "DATA_FAULT")   # a Coinbase blip is logged, not a failure
    sys.exit(0 if ok else 1)
