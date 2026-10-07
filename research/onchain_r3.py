"""
onchain_r3.py -- Research R3: does on-chain data predict returns? Rules: research/ONCHAIN_PREREG.md

Usage: python -m research.onchain_r3 fetch|test|all
Outputs (research/out/onchain/): data.json.gz (cache), R3_results.md
"""
import gzip
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(__file__), "out", "onchain")
DATA = os.path.join(OUT, "data.json.gz")
CM = "https://community-api.coinmetrics.io/v4"
FLOW_COINS = ["BTC", "ETH"]
XS_COINS = ["BTC", "ETH", "XRP", "ZEC", "QNT", "LINK", "ADA", "UNI", "XLM", "LTC", "AAVE", "BCH"]
START, SPLIT, END = "2016-06-01", "2022-01-01", "2026-09-30"


# ------------------------------------------------------------------ fetch
def cm_series(asset, metric):
    import requests
    out, token = {}, None
    while True:
        p = {"assets": asset.lower(), "metrics": metric, "frequency": "1d", "start_time": "2016-01-01",
             "end_time": END, "page_size": 10000}
        if token:
            p["next_page_token"] = token
        for _ in range(4):
            r = requests.get(CM + "/timeseries/asset-metrics", params=p, timeout=60)
            if r.status_code == 429:
                time.sleep(6)
                continue
            break
        js = r.json()
        for row in js.get("data", []):
            if row.get(metric) is not None:
                out[row["time"][:10]] = float(row[metric])
        token = js.get("next_page_token")
        if not token:
            return out
        time.sleep(0.7)


def fetch():
    from crypto_ai.market_data.coinbase import CoinbaseClient
    from research.backtest_toolbox import fetch_daily
    os.makedirs(OUT, exist_ok=True)
    d = {"metrics": {}, "closes": {}}
    for c in FLOW_COINS:
        for m in ("FlowInExNtv", "FlowOutExNtv", "SplyExNtv"):
            d["metrics"][f"{c}:{m}"] = cm_series(c, m)
            print(c, m, len(d["metrics"][f"{c}:{m}"]), flush=True)
    for c in XS_COINS:
        for m in ("AdrActCnt", "CapMVRVCur"):
            d["metrics"][f"{c}:{m}"] = cm_series(c, m)
            print(c, m, len(d["metrics"][f"{c}:{m}"]), flush=True)
    cb = CoinbaseClient()
    for c in XS_COINS:
        try:
            rows = fetch_daily(cb, f"{c}-USD", datetime(2016, 1, 1, tzinfo=timezone.utc),
                               datetime(2026, 10, 7, tzinfo=timezone.utc))
        except Exception as e:                                         # coin not on Coinbase -> excluded, reported
            print(c, "closes FAILED", e, flush=True)
            rows = []
        d["closes"][c] = {datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d"): r["close"] for r in rows}
        print(c, "closes", len(d["closes"][c]), flush=True)
    with gzip.open(DATA, "wt") as f:
        json.dump(d, f)


# ------------------------------------------------------------------ stats
def ranks(v):
    n = len(v)
    o = sorted(range(n), key=lambda i: v[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy) if sx and sy else float("nan")


def nw_t(x, lag):
    x = [v for v in x if not math.isnan(v)]
    n = len(x)
    if n < 30:
        return float("nan"), n
    m = sum(x) / n
    e = [v - m for v in x]
    s = sum(a * a for a in e) / n
    for L in range(1, lag + 1):
        s += 2 * (1 - L / (lag + 1)) * sum(e[i] * e[i - L] for i in range(L, n)) / n
    return (m / math.sqrt(s / n) if s > 0 else float("nan")), n


def ts_ic(pairs, lag):
    """Time-series rank IC with a Newey-West t: ranks standardised, product series averaged."""
    if len(pairs) < 30:
        return float("nan"), float("nan"), len(pairs)
    xs, ys = [p[1] for p in pairs], [p[2] for p in pairs]
    rx, ry = ranks(xs), ranks(ys)
    def z(v):
        m = sum(v) / len(v)
        s = math.sqrt(sum((a - m) ** 2 for a in v) / len(v))
        return [(a - m) / s for a in v]
    prod = [a * b for a, b in zip(z(rx), z(ry))]
    t, n = nw_t(prod, lag)
    return sum(prod) / len(prod), t, n


def days_between(a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def shift(d, k):
    return (date.fromisoformat(d) + timedelta(days=k)).isoformat()


def fwd(closes, d, h):
    """Return from close(d+1) to close(d+1+h): the metric of day d is only usable from d+1."""
    c0, c1 = closes.get(shift(d, 1)), closes.get(shift(d, 1 + h))
    return c1 / c0 - 1 if c0 and c1 else None


# ------------------------------------------------------------------ tests
def signals_flow(D, coin):
    fin, fout, sup = (D["metrics"][f"{coin}:{m}"] for m in ("FlowInExNtv", "FlowOutExNtv", "SplyExNtv"))
    net = {d: (fin[d] - fout[d]) / sup[d] for d in fin if d in fout and sup.get(d)}
    z = {}
    for d in net:
        past = [net.get(shift(d, -k)) for k in range(1, 31)]
        past = [p for p in past if p is not None]
        if len(past) >= 25:
            m = sum(past) / len(past)
            s = math.sqrt(sum((p - m) ** 2 for p in past) / len(past))
            if s > 0:
                z[d] = (net[d] - m) / s
    sup_chg = {d: sup[d] / sup[shift(d, -30)] - 1 for d in sup if sup.get(shift(d, -30))}
    return z, sup_chg


def xs_signal(D, coin, kind, d):
    if kind == "growth":
        aa = D["metrics"].get(f"{coin}:AdrActCnt", {})
        now = [aa.get(shift(d, -k)) for k in range(7)]
        then = [aa.get(shift(d, -30 - k)) for k in range(7)]
        if None in now or None in then or sum(then) == 0:
            return None
        return sum(now) / sum(then) - 1
    return D["metrics"].get(f"{coin}:CapMVRVCur", {}).get(d)


def run_tests(D):
    res = {}
    splits = (("DESIGN", START, shift(SPLIT, -1)), ("HOLDOUT", SPLIT, END))
    for label, lo, hi in splits:
        days = days_between(lo, hi)
        # F1, F2
        for test, h, lag in (("F1_1d", 1, 6), ("F1_7d", 7, 12), ("F2_30d", 30, 35)):
            per_coin, pooled = {}, {}
            for coin in FLOW_COINS:
                z, sc = signals_flow(D, coin)
                sig = z if test.startswith("F1") else sc
                pairs = [(d, sig[d], r) for d in days if d in sig for r in [fwd(D["closes"][coin], d, h)] if r is not None]
                per_coin[coin] = ts_ic(pairs, lag)
            # pooled = average of the two coins' standardised-rank products per day
            prods = {}
            for coin in FLOW_COINS:
                z, sc = signals_flow(D, coin)
                sig = z if test.startswith("F1") else sc
                pairs = [(d, sig[d], r) for d in days if d in sig for r in [fwd(D["closes"][coin], d, h)] if r is not None]
                if len(pairs) < 30:
                    continue
                rx, ry = ranks([p[1] for p in pairs]), ranks([p[2] for p in pairs])
                n = len(pairs)
                mx, my = sum(rx) / n, sum(ry) / n
                sx = math.sqrt(sum((a - mx) ** 2 for a in rx) / n)
                sy = math.sqrt(sum((b - my) ** 2 for b in ry) / n)
                for (d, _, _), a, b in zip(pairs, rx, ry):
                    prods.setdefault(d, []).append((a - mx) / sx * (b - my) / sy)
            series = [sum(v) / len(v) for d, v in sorted(prods.items())]
            t, n = nw_t(series, lag)
            pooled = (sum(series) / len(series) if series else float("nan"), t, n)
            res[(test, label)] = {"per_coin": per_coin, "pooled": pooled}
        # F3, F4
        for test, kind, h, lag in (("F3_growth_7d", "growth", 7, 12), ("F4_mvrv_30d", "mvrv", 30, 35)):
            ics = []
            for d in days:
                rows = []
                for coin in XS_COINS:
                    s = xs_signal(D, coin, kind, d)
                    r = fwd(D["closes"].get(coin, {}), d, h)
                    if s is not None and r is not None:
                        rows.append((s, r))
                if len(rows) >= 5:
                    m = sum(r for _, r in rows) / len(rows)
                    ics.append(spearman([s for s, _ in rows], [r - m for _, r in rows]))
                else:
                    ics.append(float("nan"))
            t, n = nw_t(ics, lag)
            valid = [v for v in ics if not math.isnan(v)]
            res[(test, label)] = {"pooled": (sum(valid) / len(valid) if valid else float("nan"), t, n)}
    return res


def economic(D, res):
    """Holdout-only economic check, direction and decile cut taken from DESIGN only."""
    out = {}
    cost = 0.009
    hold_days = days_between(SPLIT, END)
    for test, h in (("F1_1d", 1), ("F1_7d", 7), ("F2_30d", 30)):
        sign = 1 if res[(test, "DESIGN")]["pooled"][0] > 0 else -1     # +: high signal good
        lines = []
        for coin in FLOW_COINS:
            z, sc = signals_flow(D, coin)
            sig = z if test.startswith("F1") else sc
            design_vals = sorted(v for d, v in sig.items() if START <= d < SPLIT)
            if len(design_vals) < 100:
                continue
            cut = design_vals[int(0.9 * len(design_vals))] if sign < 0 else design_vals[int(0.1 * len(design_vals))]
            bad = (lambda v: v >= cut) if sign < 0 else (lambda v: v <= cut)
            cl = D["closes"][coin]
            strat, bh, out_until, switches = 1.0, 1.0, None, 0
            for d in hold_days:
                r = fwd(cl, shift(d, -1), 1)                          # close(d) -> close(d+1)
                if r is None:
                    continue
                bh *= 1 + r
                in_cash = out_until is not None and d <= out_until
                if not in_cash:
                    strat *= 1 + r
                v = sig.get(shift(d, -1))                              # yesterday's metric, usable today
                if v is not None and bad(v) and not in_cash:
                    out_until, switches = shift(d, h), switches + 1
                    strat *= 1 - cost
            lines.append((coin, strat - 1, bh - 1, switches))
        out[test] = lines
    for test, kind in (("F3_growth_7d", "growth"), ("F4_mvrv_30d", "mvrv")):
        sign = 1 if res[(test, "DESIGN")]["pooled"][0] > 0 else -1
        strat, ew, held = 1.0, 1.0, []
        for i, d in enumerate(hold_days[:-8]):
            if i % 7:
                continue
            rows = [(xs_signal(D, c, kind, shift(d, -1)), c) for c in XS_COINS]
            rows = [(s, c) for s, c in rows if s is not None and fwd(D["closes"].get(c, {}), shift(d, -1), 7) is not None]
            if len(rows) < 5:
                continue
            rows.sort(key=lambda x: -sign * x[0])
            top = [c for _, c in rows[:3]]
            r_top = sum(fwd(D["closes"][c], shift(d, -1), 7) for c in top) / 3
            r_ew = sum(fwd(D["closes"][c], shift(d, -1), 7) for _, c in rows) / len(rows)
            turnover = len(set(top) - set(held)) / 3
            strat *= (1 + r_top) * (1 - cost * turnover)
            ew *= 1 + r_ew
            held = top
        out[test] = [("top-3 vs equal-weight", strat - 1, ew - 1, None)]
    return out


def report(D):
    res = run_tests(D)
    eco = economic(D, res)
    f = lambda x: "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.3f}"
    t2 = lambda x: "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.2f}"
    lines = ["# R3 — On-chain data vs returns: results", "",
             "Rules: `research/ONCHAIN_PREREG.md` (committed before analysis). Metric of day d used from d+1. "
             "**F1/F2 use exchange labels that are backfilled: treat any F1/F2 effect as an upper bound.**", "",
             "| Test | Split | IC (pooled) | t | n | Per coin (IC, t) |", "|---|---|---|---|---|---|"]
    verdict = {}
    for test in ("F1_1d", "F1_7d", "F2_30d", "F3_growth_7d", "F4_mvrv_30d"):
        for label in ("DESIGN", "HOLDOUT"):
            r = res[(test, label)]
            ic, t, n = r["pooled"]
            pc = ", ".join(f"{c} {f(v[0])} ({t2(v[1])})" for c, v in r.get("per_coin", {}).items()) or "—"
            lines.append(f"| {test} | {label} | {f(ic)} | {t2(t)} | {n} | {pc} |")
        (icd, td, _), (ich, th, _) = res[(test, "DESIGN")]["pooled"], res[(test, "HOLDOUT")]["pooled"]
        stat_ok = (not math.isnan(td) and not math.isnan(th) and abs(td) >= 2 and abs(th) >= 2 and (td > 0) == (th > 0))
        verdict[test] = stat_ok
    lines += ["", "## Economic check (holdout only; direction and cut-offs from design)", ""]
    eco_ok = {}
    for test, rows in eco.items():
        for name, s, b, sw in rows:
            lines.append(f"- {test} {name}: rule {100 * s:+.1f}% vs {'buy & hold' if sw is not None else 'equal-weight'} "
                         f"{100 * b:+.1f}%" + (f" ({sw} exits)" if sw is not None else ""))
        eco_ok[test] = bool(rows) and all(s > b for _, s, b, _ in rows)
    lines += ["", "## Verdict (|t| ≥ 2 design AND same-sign |t| ≥ 2 holdout AND economic check)", ""]
    any_pass = False
    for test, ok in verdict.items():
        p = ok and eco_ok.get(test, False)
        any_pass |= p
        lines.append(f"- {test}: statistics {'pass' if ok else 'fail'}, economics {'pass' if eco_ok.get(test) else 'fail'} "
                     f"→ **{'PASS' if p else 'NO EVIDENCE'}**")
    lines += ["", f"**Overall: {'a test passes → candidate on-chain AI arm (forward test)' if any_pass else 'NO EVIDENCE → no on-chain arm'}.**", ""]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "R3_results.md"), "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    return any_pass


def test():
    with gzip.open(DATA, "rt") as f:
        report(json.load(f))


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("fetch", "all"):
        fetch()
    if stage in ("test", "all"):
        test()
