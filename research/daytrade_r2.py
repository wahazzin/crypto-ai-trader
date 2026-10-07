"""
daytrade_r2.py -- Research R2: do simple short-term price rules work after costs?
Rules, splits and pass criteria: research/DAYTRADE_PREREG.md (committed before any data).

Usage: python -m research.daytrade_r2 fetch|test|all
Outputs: research/out/daytrade/hourly.json.gz (data cache), R2_results.md
"""
import gzip
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "out", "daytrade")
DATA = os.path.join(OUT, "hourly.json.gz")
START = datetime(2022, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)
SPLIT = datetime(2024, 7, 1, tzinfo=timezone.utc).timestamp()
H = 3600


# ------------------------------------------------------------------ fetch
def fetch():
    from crypto_ai.lock import load_config
    from crypto_ai.market_data.coinbase import CoinbaseClient
    from crypto_ai.universe import screen
    os.makedirs(OUT, exist_ok=True)
    c = CoinbaseClient()
    u = screen(c, load_config()["universe_rule"], datetime.now(timezone.utc))
    data = {"large": u["large"], "mid": u["mid"], "candles": {}}
    for coin in u["large"] + u["mid"]:
        rows, t = {}, START.timestamp()
        while t < END.timestamp():
            t2 = min(t + 299 * H, END.timestamp())
            js = c._get(f"/products/{coin}/candles", {
                "granularity": H, "start": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(t2, timezone.utc).isoformat()})
            for r in js:
                rows[int(r[0])] = [int(r[0]), float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])]  # t,o,h,l,c,v
            t = t2 + H
            time.sleep(0.12)
        data["candles"][coin] = [rows[k] for k in sorted(rows)]
        print(f"{coin}: {len(rows)} hourly candles", flush=True)
    with gzip.open(DATA, "wt") as f:
        json.dump(data, f)


# ------------------------------------------------------------------ rules
def signals(rule, cs, i):
    """Is there an entry signal on the CLOSED candle cs[i]? cs rows: [t, o, h, l, c, v]."""
    c = cs[i][4]
    if rule == "D1":
        return i >= 24 and cs[i - 24][4] > 0 and c / cs[i - 24][4] - 1 > 0.05
    if rule == "D3":
        return i >= 1 and c / cs[i - 1][4] - 1 <= -0.03
    if rule == "D4":
        if i < 25:
            return False
        vols = sorted(r[5] for r in cs[i - 24:i])
        med = vols[len(vols) // 2]
        return med > 0 and cs[i][5] >= 4 * med and c / cs[i - 1][4] - 1 >= 0.02
    if rule == "D2":
        return False          # handled with day context in trades()
    raise ValueError(rule)


def exit_index(rule, cs, j):
    """Given entry at cs[j] open, the index of the candle whose CLOSE is the exit."""
    if rule == "D1":
        return j + 23
    if rule in ("D3", "D4"):
        return j + 5
    if rule == "D2":                                   # close of the last hour of that UTC day
        day = cs[j][0] // 86400
        k = j
        while k + 1 < len(cs) and cs[k + 1][0] // 86400 == day:
            k += 1
        return k
    raise ValueError(rule)


def trades(rule, cs):
    """List of (entry_t, gross_return, hold_hours). One open trade at a time."""
    out, i, n = [], 0, len(cs)
    day_hi = {}
    for r in cs:
        d = r[0] // 86400
        day_hi[d] = max(day_hi.get(d, 0.0), r[2])
    while i < n - 1:
        if rule == "D2":
            prev = day_hi.get(cs[i][0] // 86400 - 1)
            hit = prev is not None and cs[i][4] > prev
        else:
            hit = signals(rule, cs, i)
        j = i + 1                                      # enter at next hour's open
        if hit and j < n and cs[j][0] == cs[i][0] + H:
            k = exit_index(rule, cs, j)
            if k < n and cs[k][0] == cs[j][0] + (k - j) * H:      # no gaps inside the trade
                out.append((cs[j][0], cs[k][4] / cs[j][1] - 1, k - j + 1))
                i = k + 1
                continue
        i += 1
    return out


def cost(coin, large, fee_bps):
    slip = 2.0 if coin in ("BTC-USD", "ETH-USD") else 6.0 if coin in large else 10.0
    return 2 * (fee_bps + 5.0 + slip) / 1e4


def random_entry_mean(cs, hours, lo, hi):
    """Average gross return of ALL windows of `hours` length starting in [lo, hi)."""
    rs = [cs[j + hours - 1][4] / cs[j][1] - 1 for j in range(len(cs) - hours)
          if lo <= cs[j][0] < hi and cs[j + hours - 1][0] == cs[j][0] + (hours - 1) * H]
    return sum(rs) / len(rs) if rs else 0.0


def nw_t(x, lag=5):
    n = len(x)
    if n < 10:
        return float("nan")
    m = sum(x) / n
    e = [v - m for v in x]
    s = sum(a * a for a in e) / n
    for L in range(1, lag + 1):
        s += 2 * (1 - L / (lag + 1)) * sum(e[i] * e[i - L] for i in range(L, n)) / n
    return m / math.sqrt(s / n) if s > 0 else float("nan")


def evaluate(data):
    large = set(data["large"])
    splits = (("DESIGN 2022-01 → 2024-06", START.timestamp(), SPLIT), ("HOLDOUT 2024-07 → 2026-09", SPLIT, END.timestamp() + 1))
    res = {}
    for rule in ("D1", "D2", "D3", "D4"):
        for label, lo, hi in splits:
            rows = []
            for coin, cs in data["candles"].items():
                tr = [t for t in trades(rule, cs) if lo <= t[0] < hi]
                base = {}
                for t0, g, hrs in tr:
                    if hrs not in base:
                        base[hrs] = random_entry_mean(cs, hrs, lo, hi)
                    rows.append({"t": t0, "coin": coin, "gross": g, "excess": g - base[hrs],
                                 "net": g - cost(coin, large, 40), "net_lowfee": g - cost(coin, large, 10)})
            res[(rule, label)] = rows
    return res, splits


def summarize(rows):
    if not rows:
        return None
    by_day = defaultdict(list)
    for r in rows:
        by_day[int(r["t"] // 86400)].append(r)
    days = sorted(by_day)
    def daily(key):
        return [sum(x[key] for x in by_day[d]) / len(by_day[d]) for d in days]
    net = [r["net"] for r in rows]
    wins, losses = [x for x in net if x > 0], [x for x in net if x <= 0]
    wr = len(wins) / len(net)
    return {"n": len(rows), "win_rate": wr, "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0, "exp_net": sum(net) / len(net),
            "t_net": nw_t(daily("net")), "exp_excess": sum(r["excess"] for r in rows) / len(rows),
            "t_excess": nw_t(daily("excess")), "exp_lowfee": sum(r["net_lowfee"] for r in rows) / len(rows),
            "t_lowfee": nw_t(daily("net_lowfee"))}


def report(data):
    res, splits = evaluate(data)
    names = {"D1": "Momentum-24h (24h ret > +5%, hold 24h)", "D2": "Prior-day breakout (close > yesterday's high, exit 00:00 UTC)",
             "D3": "Flush reversal (1h ret ≤ −3%, hold 6h)", "D4": "Volume-spike continuation (vol ≥ 4× median & +2%, hold 6h)"}
    p = lambda x: "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.2f}%"
    tt = lambda x: "—" if x is None or math.isnan(x) else f"{x:+.2f}"
    lines = ["# R2 — Short-term price rules after costs: results", "",
             f"Rules: `research/DAYTRADE_PREREG.md` (committed before data). {len(data['candles'])} coins, hourly, "
             "fills at next hour's open, one open trade per coin per rule. Main costs ≈ 0.9–1.1% round trip.", ""]
    verdict = {}
    for label, _, _ in splits:
        lines += [f"## {label}", "",
                  "| Rule | Trades | Win rate | Avg win | Avg loss | **Expectancy/trade (after costs)** | t | Edge vs random entry | t | Expectancy at 10 bps fees | t |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for rule in ("D1", "D2", "D3", "D4"):
            s = summarize(res[(rule, label)])
            if not s:
                lines.append(f"| {rule} | 0 | | | | | | | | | |")
                verdict.setdefault(rule, []).append(False)
                continue
            lines.append(f"| {rule} | {s['n']} | {100 * s['win_rate']:.0f}% | {p(s['avg_win'])} | {p(s['avg_loss'])} | "
                         f"**{p(s['exp_net'])}** | {tt(s['t_net'])} | {p(s['exp_excess'])} | {tt(s['t_excess'])} | "
                         f"{p(s['exp_lowfee'])} | {tt(s['t_lowfee'])} |")
            ok = (s["n"] >= 100 and s["exp_net"] > 0 and s["t_net"] >= 2 and s["exp_excess"] > 0 and s["t_excess"] >= 2)
            verdict.setdefault(rule, []).append(ok)
        lines.append("")
    lines += ["Rules: " + "; ".join(f"**{k}** = {v}" for k, v in names.items()), "",
              "## Verdict (pre-registered: after-cost expectancy > 0 with t ≥ 2 AND edge vs random entry > 0 with t ≥ 2, "
              "≥ 100 trades, in BOTH splits)", ""]
    any_pass = False
    for rule, oks in verdict.items():
        ok = len(oks) == 2 and all(oks)
        any_pass |= ok
        lines.append(f"- {rule} {names[rule]}: design {'pass' if oks[0] else 'fail'}, holdout {'pass' if oks[1] else 'fail'} "
                     f"→ **{'PASS' if ok else 'NO EVIDENCE'}**")
    lines += ["", f"**Overall: {'a rule passes → candidate for a separately pre-registered paper day-trading arm' if any_pass else 'NO EVIDENCE → no day-trading arm from these rules'}.**", ""]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "R2_results.md"), "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return any_pass


def test():
    with gzip.open(DATA, "rt") as f:
        data = json.load(f)
    report(data)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("fetch", "all"):
        fetch()
    if stage in ("test", "all"):
        test()
