"""
backtest_toolbox.py -- does each toolbox strategy work ALONE, before any AI touches it?
(Project rule 9: test every component alone first. Rule 3: test on data it has never seen.)

WHY THIS IS ALLOWED HERE BUT NOT FOR THE AI: these strategies are plain code with fixed textbook
parameters. They can't have "memorised" history. An LLM can, so the AI is forward-tested only.

SETUP (fixed before running, not tuned afterwards)
  * Coins: today's eligible universe from the live rule (large + mid). Each coin enters the test
    once it has 120 daily candles (the same window the live bot uses).
  * Signals: computed with EXACTLY the live functions in crypto_ai/strategies/toolbox.py on the
    trailing 120 closed daily candles. Trade at that day's close.
  * Sizing like the live arms: equal weight across active coins aiming at 80% gross, caps 35% BTC/ETH,
    15% large alts, 10% mid, alts together <= 40%, 5pp rebalance band, rotation re-picks weekly.
  * Stops: 18% below entry, checked on daily lows (fills at the stop, or the open if it gapped).
  * Costs per side: 40 bps fee + 5 bps half-spread + slippage (2 bps BTC/ETH, 6 large alts, 10 mid).
  * Periods: DESIGN 2020-01-01..2023-12-31 and SEALED HOLDOUT 2024-01-01..today, reported separately.
    No parameter was chosen by looking at either.

KNOWN BIAS, STATED UP FRONT: today's universe only contains coins that SURVIVED until today
(~72% of coins ever in the top 100 are dead). That flatters every long-only result. The fair
comparison is therefore each strategy vs an EQUAL-WEIGHT HOLD OF THE SAME COINS, which carries the
same bias. A strategy that can't beat that has no edge, whatever its absolute return.

Usage: python -m research.backtest_toolbox      (needs network: Coinbase public API)
Output: research/out/backtest_toolbox.md and backtest_trades.csv
"""
import csv
import json
import math
import os
import time
from datetime import datetime, timezone

from crypto_ai.lock import load_config
from crypto_ai.market_data.coinbase import CoinbaseClient, DataFault
from crypto_ai.strategies import toolbox as T
from crypto_ai.universe import screen

OUT = os.path.join(os.path.dirname(__file__), "out")
START = datetime(2019, 6, 1, tzinfo=timezone.utc)          # 120-day warm-up before 2020
SPLIT = datetime(2024, 1, 1, tzinfo=timezone.utc)
DESIGN_FROM = datetime(2020, 1, 1, tzinfo=timezone.utc)
WINDOW = 120
STOP = 0.18
HALF_SPREAD_BPS = 5.0


def fetch_daily(client, product, start, end):
    """All daily candles between start and end (Coinbase gives max 300 per request)."""
    out, t = {}, start.timestamp()
    while t < end.timestamp():
        t2 = min(t + 299 * 86400, end.timestamp())
        params = {"granularity": 86400,
                  "start": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                  "end": datetime.fromtimestamp(t2, timezone.utc).isoformat()}
        rows = client._get(f"/products/{product}/candles", params)
        for r in rows:
            out[int(r[0])] = {"t": int(r[0]), "low": float(r[1]), "high": float(r[2]), "open": float(r[3]),
                              "close": float(r[4]), "volume": float(r[5])}
        t = t2 + 86400
        time.sleep(0.15)
    return [out[k] for k in sorted(out)]


def cost_rate(cfg, a, mid_set):
    c = cfg["costs"]
    slip = c["slippage_bps_major"] if a in cfg["majors"] else c["slippage_bps_mid"] if a in mid_set else c["slippage_bps_alt"]
    return (c["fee_bps"] + HALF_SPREAD_BPS + slip) / 1e4


def caps(cfg, a, mid_set):
    r = cfg["risk"]
    return r["max_weight_major"] if a in cfg["majors"] else r["max_weight_mid"] if a in mid_set else r["max_weight_alt"]


def target_weights(active, cfg, mid_set):
    if not active:
        return {}
    base = cfg["risk"]["max_gross_exposure"] / len(active)
    w = {a: min(base, caps(cfg, a, mid_set)) for a in active}
    alts = [a for a in w if a not in cfg["majors"]]
    s = sum(w[a] for a in alts)
    if s > cfg["risk"]["max_alt_cluster"]:
        k = cfg["risk"]["max_alt_cluster"] / s
        for a in alts:
            w[a] *= k
    return w


def simulate(name, data, dates, cfg, mid_set):
    """Daily simulation. Returns (equity series {ts: eq}, list of closed trades)."""
    cash, pos, eq_series, trades = 1.0, {}, {}, []          # pos[a] = {"units", "entry", "entry_ts", "cost_in"}
    idx = {a: {c["t"]: i for i, c in enumerate(rows)} for a, rows in data.items()}
    rot_week = None
    band = 0.05
    for ts in dates:
        bars = {a: data[a][idx[a][ts]] for a in data if ts in idx[a]}
        # stops first, on the day's low (strategies only: the hold benchmarks have no stops, like live)
        for a in list(pos) if name not in ("btc_hold", "ew_hold") else []:
            if a not in bars:
                continue
            p, b = pos[a], bars[a]
            stop = p["entry"] * (1 - STOP)
            if b["low"] <= stop:
                px = b["open"] if b["open"] <= stop else stop
                proceeds = p["units"] * px * (1 - cost_rate(cfg, a, mid_set))
                cash += proceeds
                trades.append({"strategy": name, "asset": a, "entry_ts": p["entry_ts"], "exit_ts": ts,
                               "ret": proceeds / p["cost_in"] - 1, "exit": "stop"})
                del pos[a]
        equity = cash + sum(p["units"] * bars[a]["close"] for a, p in pos.items() if a in bars)
        # signals on the trailing window (same functions as live)
        eligible = [a for a in bars if idx[a][ts] + 1 >= WINDOW]
        hist = {a: data[a][idx[a][ts] + 1 - WINDOW: idx[a][ts] + 1] for a in eligible}
        if name == "ew_hold":
            day = datetime.fromtimestamp(ts, timezone.utc)
            rebalance = day.day == 1 or not pos
            active = eligible
        elif name == "btc_hold":
            rebalance, active = not pos, ["BTC-USD"] if "BTC-USD" in eligible else []
        else:
            sig = T.compute_signals(hist, eligible, cfg)
            active = [a for a in eligible if T.is_on(sig[a], name)]
            rebalance = True
            if name == "rotation":
                day = datetime.fromtimestamp(ts, timezone.utc)
                wk = day.strftime("%G-W%V")
                rebalance = (day.weekday() == 0 or rot_week is None) and wk != rot_week
                if rebalance:
                    rot_week = wk
        if rebalance and equity > 0:
            if name == "ew_hold":
                tw = {a: 0.995 / len(active) for a in active} if active else {}
            elif name == "btc_hold":
                tw = {"BTC-USD": 0.995} if active else {}
            else:
                tw = target_weights(active, cfg, mid_set)
            cur = {a: p["units"] * bars[a]["close"] / equity for a, p in pos.items() if a in bars}
            for a in list(pos):                                   # sells
                if a not in bars:
                    continue
                t_w = tw.get(a, 0.0)
                if t_w <= 0 or cur[a] - t_w > band:
                    p = pos[a]
                    sell_units = p["units"] if t_w <= 0 else p["units"] * (1 - t_w / cur[a])
                    proceeds = sell_units * bars[a]["close"] * (1 - cost_rate(cfg, a, mid_set))
                    cash += proceeds
                    if t_w <= 0:
                        trades.append({"strategy": name, "asset": a, "entry_ts": p["entry_ts"], "exit_ts": ts,
                                       "ret": (proceeds + 0) / p["cost_in"] - 1, "exit": "signal"})
                        del pos[a]
                    else:
                        frac = sell_units / p["units"]
                        p["units"] -= sell_units
                        p["cost_in"] *= (1 - frac)
            for a, t_w in tw.items():                             # buys
                c_w = cur.get(a, 0.0) if a in pos else 0.0
                if t_w - c_w > (band if a in pos else 0.0):
                    spend = min((t_w - c_w) * equity, cash)
                    if spend <= 1e-9:
                        continue
                    units = spend * (1 - cost_rate(cfg, a, mid_set)) / bars[a]["close"]
                    cash -= spend
                    if a in pos:
                        p = pos[a]
                        p["entry"] = (p["entry"] * p["units"] + bars[a]["close"] * units) / (p["units"] + units)
                        p["units"] += units
                        p["cost_in"] += spend
                    else:
                        pos[a] = {"units": units, "entry": bars[a]["close"], "entry_ts": ts, "cost_in": spend}
        eq_series[ts] = cash + sum(p["units"] * bars[a]["close"] for a, p in pos.items() if a in bars)
    return eq_series, trades


def stats(eq, trades, t_from, t_to):
    ks = [k for k in sorted(eq) if t_from <= k < t_to]
    if len(ks) < 30:
        return None
    vals = [eq[k] for k in ks]
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1] > 0]
    years = (ks[-1] - ks[0]) / (365.25 * 86400)
    total = vals[-1] / vals[0] - 1
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    tr = [t for t in trades if t_from <= t["exit_ts"] < t_to]
    wins = [t["ret"] for t in tr if t["ret"] > 0]
    losses = [t["ret"] for t in tr if t["ret"] <= 0]
    wr = len(wins) / len(tr) if tr else float("nan")
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    return {"total": total, "cagr": (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else float("nan"),
            "sharpe": mu / sd * math.sqrt(365) if sd > 0 else float("nan"), "maxdd": mdd,
            "trades": len(tr), "win_rate": wr, "avg_win": aw, "avg_loss": al,
            "expectancy": (wr * aw + (1 - wr) * al) if tr else float("nan")}


def pct(x):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.1f}%"


def main():
    cfg = load_config()
    client = CoinbaseClient()
    now = datetime.now(timezone.utc)
    uni = screen(client, cfg["universe_rule"], now)
    coins, mid_set = uni["large"] + uni["mid"], set(uni["mid"])
    data = {}
    for a in coins:
        try:
            rows = fetch_daily(client, a, START, now)
        except DataFault as e:
            print(f"skip {a}: {e}")
            continue
        rows = [r for r in rows if r["t"] + 86400 <= now.timestamp()]   # closed candles only
        if len(rows) > WINDOW:
            data[a] = rows
        print(f"{a}: {len(rows)} days from {datetime.fromtimestamp(rows[0]['t'], timezone.utc).date() if rows else '-'}")
    dates = sorted({r["t"] for rows in data.values() for r in rows})
    results, all_trades = {}, []
    for name in ("btc_hold", "ew_hold") + T.NAMES:
        eq, tr = simulate(name, data, dates, cfg, mid_set)
        results[name] = (eq, tr)
        all_trades += tr
        print(f"simulated {name}: {len(tr)} closed trades")

    periods = [("DESIGN 2020-2023", DESIGN_FROM.timestamp(), SPLIT.timestamp()),
               ("HOLDOUT 2024-today", SPLIT.timestamp(), now.timestamp() + 1)]
    os.makedirs(OUT, exist_ok=True)
    lines = [f"# Toolbox backtest — each strategy alone ({now:%Y-%m-%d %H:%M UTC})", "",
             f"Coins ({len(data)}): {', '.join(data)}", "",
             "Costs per side: 40 bps fee + 5 bps half-spread + 2/6/10 bps slippage. Stop 18%. "
             "Parameters fixed before the run, never tuned.", "",
             "**Survivorship bias:** only coins alive today are included, which flatters everything. "
             "Judge strategies against `ew_hold` (same coins, same bias), not by absolute return.", ""]
    for label, f, t in periods:
        lines += [f"## {label}", "",
                  "| Strategy | Total | CAGR | Sharpe | Max DD | Trades | Win rate | Avg win | Avg loss | Expectancy/trade | Beats EW hold? |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        ew = stats(*results["ew_hold"], f, t)
        for name, (eq, tr) in results.items():
            s = stats(eq, tr, f, t)
            if not s:
                continue
            beats = "—" if name in ("ew_hold", "btc_hold") or not ew else ("YES" if s["sharpe"] > ew["sharpe"] and s["total"] > ew["total"] else "no")
            lines.append(f"| {name} | {pct(s['total'])} | {pct(s['cagr'])} | {s['sharpe']:.2f} | {pct(s['maxdd'])} | "
                         f"{s['trades']} | {pct(s['win_rate'])} | {pct(s['avg_win'])} | {pct(s['avg_loss'])} | "
                         f"{pct(s['expectancy'])} | {beats} |")
        lines.append("")
    # ---- signal audit: are the signals sane? (how often each is on, and raw candles for 3 coins)
    on_count = {n: 0 for n in T.NAMES}
    coin_days = 0
    for ts in dates[WINDOW::7]:                          # weekly sample is plenty for a rate
        elig = [a for a in data if any(r["t"] == ts for r in data[a])]
        hist = {}
        for a in elig:
            i = next(k for k, r in enumerate(data[a]) if r["t"] == ts)
            if i + 1 >= WINDOW:
                hist[a] = data[a][i + 1 - WINDOW:i + 1]
        if not hist:
            continue
        sig = T.compute_signals(hist, list(hist), cfg)
        coin_days += len(hist)
        for a in hist:
            for n in T.NAMES:
                on_count[n] += T.is_on(sig[a], n)
    lines += ["## Signal audit", "", "Share of coin-days each signal was ON (weekly sample, all years):", ""]
    lines += [f"- {n}: {100 * on_count[n] / max(coin_days, 1):.1f}%" for n in T.NAMES]
    last = {a: rows[-WINDOW:] for a, rows in data.items()}
    sig_now = T.compute_signals(last, list(last), cfg)
    for a in [x for x in ("BTC-USD", "UNI-USD", "AERO-USD") if x in data]:
        lines += ["", f"### {a} — signals now: " + json.dumps({n: sig_now[a][n] for n in T.NAMES}), "",
                  "| Date | Open | High | Low | Close | Volume |", "|---|---|---|---|---|---|"]
        for r in data[a][-25:]:
            lines.append(f"| {datetime.fromtimestamp(r['t'], timezone.utc).date()} | {r['open']:.4g} | {r['high']:.4g} | "
                         f"{r['low']:.4g} | {r['close']:.4g} | {r['volume']:.4g} |")
    lines.append("")
    lines += ["“Beats EW hold” = higher Sharpe AND higher total return than holding the same coins equally. "
              "Expectancy = win rate × avg win + loss rate × avg loss, per closed trade, after costs.", ""]
    with open(os.path.join(OUT, "backtest_toolbox.md"), "w") as fh:
        fh.write("\n".join(lines))
    with open(os.path.join(OUT, "backtest_trades.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["strategy", "asset", "entry_ts", "exit_ts", "ret", "exit"])
        w.writeheader()
        w.writerows(all_trades)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
