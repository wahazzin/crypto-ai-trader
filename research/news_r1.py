"""
news_r1.py -- Research R1: does crypto news predict crypto returns? (rules: research/NEWS_PREREG.md)

Stages (each saves to research/out/news/ so the next stage can resume from the research branch):
  fetch   headlines for today's eligible coins from Alpaca News (Benzinga), 2021-01-01 .. 2026-09-30
  score   FinBERT (ProsusAI/finbert) on every unique headline: P(positive) - P(negative)
  test    T1/T2/T3 exactly as pre-registered; design split first, holdout second; writes R1_results.md

Usage: python -m research.news_r1 fetch|score|test|all
"""
import gzip
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

OUT = os.path.join(os.path.dirname(__file__), "out", "news")
HEAD = os.path.join(OUT, "headlines.jsonl.gz")
SCORES = os.path.join(OUT, "finbert_scores.json")
PRICES = os.path.join(OUT, "daily_closes.json")
START = datetime(2021, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
SPLIT = "2024-07-01"


def coins():
    from crypto_ai.lock import load_config
    from crypto_ai.market_data.coinbase import CoinbaseClient
    from crypto_ai.universe import screen
    u = screen(CoinbaseClient(), load_config()["universe_rule"], datetime.now(timezone.utc))
    return u["large"] + u["mid"]


# ------------------------------------------------------------------ fetch
def fetch():
    os.makedirs(OUT, exist_ok=True)
    uni = coins()
    sym = {c.replace("-", ""): c for c in uni}                       # BTCUSD -> BTC-USD
    h = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
    seen, n_req = {}, 0
    for i in range(0, len(sym), 10):                                  # 10 symbols per query
        batch = list(sym)[i:i + 10]
        token = None
        while True:
            p = {"symbols": ",".join(batch), "start": START.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "end": END.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 50, "sort": "asc", "include_content": "false"}
            if token:
                p["page_token"] = token
            for attempt in range(5):
                r = requests.get("https://data.alpaca.markets/v1beta1/news", headers=h, params=p, timeout=60)
                if r.status_code == 429:
                    time.sleep(20)
                    continue
                break
            r.raise_for_status()
            n_req += 1
            js = r.json()
            for a in js.get("news", []):
                tags = sorted({sym[s] for s in a.get("symbols", []) if s in sym})
                if tags:
                    seen[a["id"]] = {"id": a["id"], "t": a["created_at"], "h": a["headline"], "coins": tags,
                                     "n_symbols": len(a.get("symbols", []))}
            token = js.get("next_page_token")
            if not token:
                break
            time.sleep(0.32)                                          # ~190 requests/min < 200 limit
        print(f"batch {i // 10 + 1}: {len(seen)} unique headlines so far ({n_req} requests)", flush=True)
    rows = sorted(seen.values(), key=lambda r: r["t"])
    with gzip.open(HEAD, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    # prices for the same coins (closed daily candles)
    from crypto_ai.market_data.coinbase import CoinbaseClient
    from research.backtest_toolbox import fetch_daily
    c = CoinbaseClient()
    closes = {}
    for coin in uni:
        rows_p = fetch_daily(c, coin, START - timedelta(days=5), END + timedelta(days=10))
        closes[coin] = {datetime.fromtimestamp(x["t"], timezone.utc).strftime("%Y-%m-%d"): x["close"] for x in rows_p}
    with open(PRICES, "w") as f:
        json.dump(closes, f)
    per_coin = defaultdict(int)
    per_year = defaultdict(int)
    for r in rows:
        per_year[r["t"][:4]] += 1
        for cc in r["coins"]:
            per_coin[cc] += 1
    summary = {"headlines": len(rows), "requests": n_req, "per_year": dict(per_year), "per_coin": dict(per_coin),
               "multi_coin_share": sum(len(r["coins"]) > 1 for r in rows) / max(len(rows), 1),
               "first": rows[0]["t"] if rows else None}
    with open(os.path.join(OUT, "fetch_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


def load_headlines():
    with gzip.open(HEAD, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


# ------------------------------------------------------------------ score
def score():
    from transformers import pipeline                                # installed only for this stage
    rows = load_headlines()
    done = json.load(open(SCORES)) if os.path.exists(SCORES) else {}
    todo = list({r["h"] for r in rows if r["h"] not in done})
    print(f"{len(rows)} headlines, {len(done)} already scored, {len(todo)} to score", flush=True)
    clf = pipeline("text-classification", model="ProsusAI/finbert", top_k=None, truncation=True, device=-1)
    t0 = time.time()
    for i in range(0, len(todo), 64):
        chunk = todo[i:i + 64]
        for text, res in zip(chunk, clf(chunk, batch_size=64)):
            p = {d["label"].lower(): d["score"] for d in res}
            done[text] = round(p.get("positive", 0) - p.get("negative", 0), 4)
        if (i // 64) % 50 == 0:
            print(f"  {i + len(chunk)}/{len(todo)} ({(i + len(chunk)) / max(time.time() - t0, 1):.0f}/s)", flush=True)
            with open(SCORES, "w") as f:
                json.dump(done, f)
    with open(SCORES, "w") as f:
        json.dump(done, f)
    print(f"scored {len(todo)} in {time.time() - t0:.0f}s")


# ------------------------------------------------------------------ test
def spearman(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    def rank(v):
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
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy) if sx and sy else float("nan")


def nw_t(series, lag=5):
    """t-stat of the mean with Newey-West standard errors."""
    x = [v for v in series if not math.isnan(v)]
    n = len(x)
    if n < 10:
        return float("nan"), n
    m = sum(x) / n
    e = [v - m for v in x]
    s = sum(a * a for a in e) / n
    for L in range(1, lag + 1):
        w = 1 - L / (lag + 1)
        s += 2 * w * sum(e[i] * e[i - L] for i in range(L, n)) / n
    return (m / math.sqrt(s / n) if s > 0 else float("nan")), n


def test():
    rows = load_headlines()
    sc = json.load(open(SCORES))
    closes = json.load(open(PRICES))
    days = sorted({d for c in closes.values() for d in c})
    day_i = {d: i for i, d in enumerate(days)}
    # excess return of coin over equal-weight universe, close(d) -> close(d+h)
    def fwd(coin, d, h):
        i = day_i.get(d)
        if i is None:
            return None
        if i + h >= len(days):
            return None
        d1 = days[i + h]
        c0, c1 = closes[coin].get(d), closes[coin].get(d1)
        return c1 / c0 - 1 if c0 and c1 else None
    ew_cache = {}
    def ew(d, h):
        k = (d, h)
        if k not in ew_cache:
            rs = [r for r in (fwd(c, d, h) for c in closes) if r is not None]
            ew_cache[k] = sum(rs) / len(rs) if rs else None
        return ew_cache[k]
    def xs(coin, d, h):
        r, m = fwd(coin, d, h), ew(d, h)
        return None if r is None or m is None else r - m
    # coin-day aggregates
    agg = defaultdict(list)
    for r in rows:
        s = sc.get(r["h"])
        if s is None:
            continue
        for c in r["coins"]:
            agg[(c, r["t"][:10])].append(s)
    counts = defaultdict(int)
    for (c, d), v in agg.items():
        counts[(c, d)] = len(v)
    lines = ["# R1 — Crypto news vs returns: results", "",
             f"Rules: `research/NEWS_PREREG.md` (committed before data). {len(rows)} headlines, "
             f"{len(agg)} coin-days with news, {len(closes)} coins.", ""]
    verdicts = {}
    for label, lo, hi in (("DESIGN (→2024-06-30)", "0000", SPLIT), ("HOLDOUT (2024-07-01→2026-09-30)", SPLIT, "9999")):
        lines += [f"## {label}", ""]
        # T1 pooled IC by day-ordered series of per-day pooled ICs
        for h in (1, 3):
            by_day = defaultdict(lambda: ([], []))
            for (c, d), v in agg.items():
                if lo <= d < hi:
                    x = xs(c, d, h)
                    if x is not None:
                        by_day[d][0].append(sum(v) / len(v))
                        by_day[d][1].append(x)
            allx = [a for d in sorted(by_day) for a in by_day[d][0]]
            ally = [b for d in sorted(by_day) for b in by_day[d][1]]
            ic = spearman(allx, ally)
            # NW t on daily mean of (rank-free) sentiment*return products -> use daily ICs where n>=3 else skip
            daily = [spearman(*by_day[d]) for d in sorted(by_day) if len(by_day[d][0]) >= 3]
            t2, nd = nw_t(daily)
            mean_daily = sum(v for v in daily if not math.isnan(v)) / max(sum(1 for v in daily if not math.isnan(v)), 1)
            # pooled t approximation with NW over daily-average products
            prod = [sum((a - 0) * b for a, b in zip(*by_day[d])) / len(by_day[d][0]) for d in sorted(by_day)]
            t1, n1 = nw_t(prod)
            lines.append(f"- **T1 avg sentiment → next {h}d excess return:** pooled IC {ic:+.4f} "
                         f"(n={len(allx)} coin-days), NW t of daily sentiment×return = {t1:+.2f} ({n1} days)")
            lines.append(f"- **T2 cross-sectional, next {h}d:** mean daily IC {mean_daily:+.4f}, NW t {t2:+.2f} ({nd} days with ≥3 coins)")
            verdicts.setdefault(f"T1_{h}d", []).append((t1, None))
            verdicts.setdefault(f"T2_{h}d", []).append((t2, mean_daily))
        # T3 attention shocks
        med = {}
        for c in closes:
            v = sorted(n for (cc, d), n in counts.items() if cc == c)
            med[c] = v[len(v) // 2] if v else None
        shocks = sorted((d, c) for (c, d), n in counts.items() if lo <= d < hi and med.get(c) and n >= 3 * med[c])
        last = {}
        declust = []
        for d, c in shocks:
            if c not in last or (datetime.fromisoformat(d) - datetime.fromisoformat(last[c])).days >= 10:
                declust.append((d, c))
                last[c] = d
        lines.append(f"- **T3 attention shocks** (≥3× coin's median news count): {len(shocks)} shock-days, "
                     f"{len(declust)} after declustering (≥10 days apart per coin)")
        for h in (1, 3, 7):
            for name, ev in (("all", shocks), ("declustered", declust)):
                xsr = [x for x in (xs(c, d, h) for d, c in ev) if x is not None]
                if len(xsr) > 2:
                    m = sum(xsr) / len(xsr)
                    sd = math.sqrt(sum((v - m) ** 2 for v in xsr) / (len(xsr) - 1))
                    t = m / (sd / math.sqrt(len(xsr))) if sd else float("nan")
                else:
                    m, t = float("nan"), float("nan")
                lines.append(f"  - next {h}d excess, {name}: mean {100 * m:+.2f}% (t {t:+.2f}, n={len(xsr)})")
                if name == "declustered":
                    verdicts.setdefault(f"T3_{h}d", []).append((t, m))
            # sentiment terciles on declustered shocks
            sv = sorted((sum(agg[(c, d)]) / len(agg[(c, d)]), xs(c, d, h)) for d, c in declust if xs(c, d, h) is not None)
            if len(sv) >= 9:
                k = len(sv) // 3
                parts = {"neg": sv[:k], "mid": sv[k:2 * k], "pos": sv[2 * k:]}
                lines.append("    - by sentiment tercile: " + ", ".join(
                    f"{nm} {100 * sum(y for _, y in p) / len(p):+.2f}% (n={len(p)})" for nm, p in parts.items()))
        lines.append("")
    # verdicts per pre-registered rule
    lines += ["## Verdict (pre-registered rule: |t|≥2 in design AND same-sign |t|≥2 in holdout AND beats ~1% round trip)", ""]
    any_pass = False
    for k, v in verdicts.items():
        if len(v) < 2:
            continue
        (td, md), (th, mh) = v[0], v[1]
        big_enough = k.startswith("T3") and mh is not None and not math.isnan(mh) and abs(mh) >= 0.01
        ok = (not math.isnan(td) and not math.isnan(th) and abs(td) >= 2 and abs(th) >= 2
              and (td > 0) == (th > 0) and (big_enough or not k.startswith("T3")))
        if k.startswith(("T1", "T2")) and ok:
            ok_note = " (statistically passes; economic size checked separately)"
        else:
            ok_note = ""
        any_pass |= ok
        lines.append(f"- {k}: design t {td:+.2f}, holdout t {th:+.2f} → **{'PASS' if ok else 'NO EVIDENCE'}**{ok_note}")
    lines += ["", f"**Overall: {'at least one test passes → design an ai_news arm (still forward-tested)' if any_pass else 'NO EVIDENCE → no news arm'}.**", ""]
    with open(os.path.join(OUT, "R1_results.md"), "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("fetch", "all"):
        fetch()
    if stage in ("score", "all"):
        score()
    if stage in ("test", "all"):
        test()
