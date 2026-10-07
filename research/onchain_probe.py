"""
onchain_probe.py -- what free on-chain data exists for our coins? READ-ONLY feasibility check
before any on-chain research is designed (research R3).

Source: Coin Metrics Community API (free, no key; licence CC BY-NC = fine for non-commercial
research). For each of our coins: which daily metrics exist and from when; then spot-checks the
metrics an on-chain test would need (exchange flows / exchange supply / active addresses).
Output: research/out/onchain/probe.md
"""
import json
import os
import time

import requests

BASE = "https://community-api.coinmetrics.io/v4"
OUT = os.path.join(os.path.dirname(__file__), "out", "onchain")
WANT = ["AdrActCnt", "TxCnt", "FlowInExNtv", "FlowOutExNtv", "FlowInExUSD", "FlowOutExUSD", "SplyExNtv",
        "CapMVRVCur", "FeeTotNtv", "NVTAdj", "SplyAct1d", "HashRate"]


def get(path, params):
    for _ in range(3):
        r = requests.get(BASE + path, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(6)
            continue
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300])
    return r.status_code, r.text[:300]


def main():
    from datetime import datetime, timezone
    from crypto_ai.lock import load_config
    from crypto_ai.market_data.coinbase import CoinbaseClient
    from crypto_ai.universe import screen
    os.makedirs(OUT, exist_ok=True)
    u = screen(CoinbaseClient(), load_config()["universe_rule"], datetime.now(timezone.utc))
    coins = [c.split("-")[0].lower() for c in u["large"] + u["mid"]]
    lines = [f"# On-chain data probe ({datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}) — Coin Metrics Community", ""]
    code, cat = get("/catalog-v2/asset-metrics", {"assets": ",".join(coins), "page_size": 10000})
    if code != 200:
        lines.append(f"catalog HTTP {code}: {str(cat)[:300]}")
    else:
        lines += ["| Coin | # daily metrics | Wanted metrics available (from) |", "|---|---|---|"]
        for a in cat.get("data", []):
            daily = {}
            for m in a.get("metrics", []):
                for f in m.get("frequencies", []):
                    if f.get("frequency") == "1d":
                        daily[m["metric"]] = f.get("min_time", "")[:10]
            have = [f"{w} ({daily[w]})" for w in WANT if w in daily]
            lines.append(f"| {a['asset'].upper()} | {len(daily)} | {', '.join(have) or '—'} |")
        missing = sorted(set(coins) - {a["asset"] for a in cat.get("data", [])})
        lines += ["", f"Coins with no community data at all: {', '.join(c.upper() for c in missing) or 'none'}", ""]
    # spot check: can we actually pull a long daily series?
    lines += ["## Spot check: BTC & ETH daily series since 2021", ""]
    for asset in ("btc", "eth"):
        for m in ("FlowInExNtv", "SplyExNtv", "AdrActCnt"):
            code, js = get("/timeseries/asset-metrics", {"assets": asset, "metrics": m, "frequency": "1d",
                                                         "start_time": "2021-01-01", "page_size": 10000})
            if code == 200 and js.get("data"):
                d = js["data"]
                lines.append(f"- {asset.upper()} {m}: {len(d)} days, {d[0]['time'][:10]} → {d[-1]['time'][:10]}, "
                             f"last value {d[-1].get(m)}")
            else:
                lines.append(f"- {asset.upper()} {m}: HTTP {code} {str(js)[:160]}")
            time.sleep(0.7)
    with open(os.path.join(OUT, "probe.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
