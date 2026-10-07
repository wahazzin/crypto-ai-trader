"""
toolbox.py -- four well-known swing strategies, written as plain code.

Each strategy is used twice:
  1. its signal is SHOWN to the AI every cycle (as evidence, not orders)
  2. it trades ALONE in its own paper portfolio (s_trend, s_breakout, s_dip, s_rotation), through
     the same risk engine and costs as the AI. If an AI can't beat the best of these, it adds
     nothing.

DESIGN RULES
  * Stateless: every signal is recomputed from closed DAILY candles only. Same candles in, same
    signal out. That's what makes these strategies backtestable (no AI inside, so no memorised
    history problem), with exactly the code that trades live.
  * Parameters are textbook defaults, fixed BEFORE any test. They are not tuned. Tuning on the
    data we then test on is how overfit backtests are made (project rule 3).
  * A coin that is no longer eligible (dropped out of the universe) gets no signal, so the
    strategy arms exit it.

THE FOUR STRATEGIES (params in experiment.json -> strategies)
  trend      close > SMA50 AND SMA50 higher than 10 days ago. "Ride established uptrends."
  breakout   enter when close > the highest high of the prior 20 days on >= 1.5x average volume;
             exit when close < the lowest low of the prior 10 days. (Donchian-style.)
  dip        in an uptrend (SMA50 rising), enter after a >= 8% drop over 3 days while still within
             10% of SMA50; exit when close > SMA10 or after 10 days. "Buy panic in a healthy trend."
  rotation   rank eligible coins by 28-day return; hold the top 3 with a positive return.
             Re-picked once a week (Monday 00:00 UTC cycle) to keep fees down.
             Momentum is one of the 3 factors in Liu, Tsyvinski & Wu (J. Finance 2022).
"""
from crypto_ai.risk.engine import Proposal

NAMES = ("trend", "breakout", "dip", "rotation")


def _sma(x, n, end=None):
    end = len(x) if end is None else end
    if end < n:
        return None
    return sum(x[end - n:end]) / n


def trend_signal(daily, p):
    c = [d["close"] for d in daily]
    n, lb = p["sma_days"], p["slope_lookback_days"]
    if len(c) < n + lb:
        return {"on": False, "reason": "not enough history"}
    s_now, s_then = _sma(c, n), _sma(c, n, len(c) - lb)
    on = c[-1] > s_now and s_now > s_then
    return {"on": on, "close_vs_sma50_pct": round(100 * (c[-1] / s_now - 1), 2),
            "sma50_slope_pct": round(100 * (s_now / s_then - 1), 2)}


def breakout_signal(daily, p):
    """Replays the entry/exit rules over the candle history to know whether a trade is open now."""
    hi_n, lo_n, vm = p["entry_high_days"], p["exit_low_days"], p["volume_mult"]
    start = max(hi_n, lo_n)
    if len(daily) <= start:
        return {"on": False, "reason": "not enough history"}
    in_trade, entry_i = False, None
    for i in range(start, len(daily)):
        d = daily[i]
        prior = daily[i - hi_n:i]
        if not in_trade:
            avg_v = sum(x["volume"] for x in prior) / hi_n
            if d["close"] > max(x["high"] for x in prior) and avg_v > 0 and d["volume"] >= vm * avg_v:
                in_trade, entry_i = True, i
        elif d["close"] < min(x["low"] for x in daily[i - lo_n:i]):
            in_trade, entry_i = False, None
    out = {"on": in_trade}
    if in_trade:
        out["days_in_trade"] = len(daily) - 1 - entry_i
    return out


def dip_signal(daily, p):
    c = [d["close"] for d in daily]
    n, lb = p["trend_sma_days"], p["slope_lookback_days"]
    start = n + lb
    if len(c) <= start:
        return {"on": False, "reason": "not enough history"}
    in_trade, entry_i = False, None
    for i in range(start, len(c)):
        s, s_then = _sma(c, n, i + 1), _sma(c, n, i + 1 - lb)
        if not in_trade:
            drop = c[i] / max(c[i - p["drop_days"]:i]) - 1
            if s > s_then and drop <= -p["drop_pct"] / 100 and c[i] >= s * (1 - p["max_below_sma_pct"] / 100):
                in_trade, entry_i = True, i
        else:
            if c[i] > _sma(c, p["exit_sma_days"], i + 1) or i - entry_i >= p["max_hold_days"]:
                in_trade, entry_i = False, None
    out = {"on": in_trade}
    if in_trade:
        out["days_in_trade"] = len(c) - 1 - entry_i
    return out


def rotation_ranks(daily_by_asset, eligible, p):
    """28-day return rank among eligible coins. Returns {asset: {"rank", "ret_28d_pct", "pick"}}."""
    lb = p["lookback_days"]
    rets = {}
    for a in eligible:
        c = [d["close"] for d in daily_by_asset.get(a, [])]
        if len(c) > lb:
            rets[a] = c[-1] / c[-1 - lb] - 1
    order = sorted(rets, key=lambda a: -rets[a])
    out = {}
    for i, a in enumerate(order, 1):
        out[a] = {"rank": i, "ret_28d_pct": round(100 * rets[a], 2),
                  "pick": i <= p["top_n"] and rets[a] > 0}
    return out


def compute_signals(daily_by_asset, eligible, cfg):
    """{asset: {"trend": {...}, "breakout": {...}, "dip": {...}, "rotation": {...}}} for eligible coins."""
    sp = cfg["strategies"]
    rot = rotation_ranks(daily_by_asset, eligible, sp["rotation"])
    out = {}
    for a in eligible:
        d = daily_by_asset.get(a, [])
        out[a] = {"trend": trend_signal(d, sp["trend"]),
                  "breakout": breakout_signal(d, sp["breakout"]),
                  "dip": dip_signal(d, sp["dip"]),
                  "rotation": rot.get(a, {"rank": None, "pick": False})}
    return out


def is_on(sig, name):
    s = sig.get(name, {})
    return bool(s.get("pick") if name == "rotation" else s.get("on"))


def signal_count(sig):
    return sum(is_on(sig, n) for n in NAMES)


def mid_candidates(signals, mid, held, k):
    """Mid coins the AI-Large+Mid arm gets to look at: anything it already holds, plus the top
    `k` mid coins by number of active signals (ties -> better rotation rank). Non-trend signals
    rank first because trend alone fires on most coins in a bull market."""
    def score(a):
        s = signals[a]
        strong = sum(is_on(s, n) for n in ("breakout", "dip", "rotation"))
        return (-strong, -is_on(s, "trend"), s["rotation"].get("rank") or 999)
    held_mid = [a for a in held if a in mid]
    cands = sorted((a for a in mid if a in signals and a not in held_mid and signal_count(signals[a]) > 0),
                   key=score)
    return held_mid + cands[:k]


def strategy_proposals(arm, name, pf, signals, snapshot, cfg, now):
    """Turn one strategy's signals into proposals for its own arm. Equal weight across active
    coins, aiming at the same 80% gross the AI faces; the risk engine clips like any other arm.
    Rotation only re-picks on the Monday 00:00 UTC cycle."""
    spec = cfg["arms"][arm]
    assets = snapshot["assets"]
    mids = {a: v["mid"] for a, v in assets.items()}
    cur = pf.weights(mids)
    if name == "rotation":
        week = now.strftime("%G-W%V")
        rebalance_now = (now.weekday() == 0 and now.hour < 6) or not pf.extra.get("rotation_week")
        if not rebalance_now or pf.extra.get("rotation_week") == week:
            return []
        pf.extra["rotation_week"] = week
    active = [a for a, s in signals.items() if is_on(s, name) and a in assets]
    target = cfg["risk"]["max_gross_exposure"] / len(active) if active else 0.0
    band, props = spec["band"], []
    for a in sorted(set(active) | set(k for k, w in cur.items() if w > 1e-4)):
        w = cur.get(a, 0.0)
        if a in active:
            if w <= 1e-4:
                props.append(Proposal(arm, a, "BUY", target, None, "strategy"))
            elif target - w > band:
                props.append(Proposal(arm, a, "ADD", target, None, "strategy"))
            elif w - target > band:
                props.append(Proposal(arm, a, "REDUCE", target, None, "strategy"))
        elif w > 1e-4:
            props.append(Proposal(arm, a, "EXIT", None, None, "strategy"))
    return props


def signals_for_prompt(signals, assets):
    """Compact view of the toolbox for the AI, only for the coins it can see."""
    out = {}
    for a in assets:
        s = signals.get(a)
        if not s:
            continue
        out[a] = {"trend": s["trend"].get("on"), "breakout": s["breakout"].get("on"),
                  "dip": s["dip"].get("on"), "rotation_pick": s["rotation"].get("pick"),
                  "rotation_rank": s["rotation"].get("rank"),
                  "ret_28d_pct": s["rotation"].get("ret_28d_pct")}
        for k in ("breakout", "dip"):
            if s[k].get("days_in_trade") is not None:
                out[a][f"{k}_days_in_trade"] = s[k]["days_in_trade"]
    return out
