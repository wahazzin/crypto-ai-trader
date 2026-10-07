"""
alpaca_probe.py -- what can this Alpaca paper account actually do? READ-ONLY: places no orders.

Checks: account status + crypto permission (never prints account number/id), which of the bot's
eligible coins Alpaca lists as tradable, SPY daily bars (rule 5 benchmark), crypto news coverage
(live + historical, for the sentiment backtest). Output: research/out/alpaca_probe.md

Keys come from env ALPACA_API_KEY / ALPACA_SECRET_KEY (GitHub Secrets). Never printed.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from crypto_ai.lock import load_config
from crypto_ai.market_data.coinbase import CoinbaseClient
from crypto_ai.universe import screen

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
OUT = os.path.join(os.path.dirname(__file__), "out")


def get(base, path, params=None):
    h = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
    r = requests.get(base + path, headers=h, params=params or {}, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300])


def main():
    lines = [f"# Alpaca probe ({datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}) — read-only", ""]
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")):
        lines.append("**ALPACA_API_KEY / ALPACA_SECRET_KEY not set in this run.**")
        return lines

    code, acct = get(PAPER, "/v2/account")
    lines += ["## Account", ""]
    if code != 200:
        lines.append(f"HTTP {code}: {acct}")
        return lines
    keep = ("status", "crypto_status", "currency", "trading_blocked", "account_blocked", "pattern_day_trader",
            "shorting_enabled", "multiplier", "crypto_tier")
    for k in keep:
        lines.append(f"- {k}: `{acct.get(k)}`")
    lines.append(f"- paper equity: `{acct.get('equity')}` (cash `{acct.get('cash')}`)")

    code, assets = get(PAPER, "/v2/assets", {"asset_class": "crypto", "status": "active"})
    lines += ["", "## Crypto coins Alpaca lists vs our eligible universe", ""]
    tradable = {}
    if code == 200:
        for a in assets:
            tradable[a["symbol"].replace("/", "-")] = a.get("tradable")
        lines.append(f"Alpaca active crypto pairs: {len(assets)} (USD pairs: {sum(1 for s in tradable if s.endswith('-USD'))})")
    else:
        lines.append(f"assets HTTP {code}: {assets}")
    try:
        uni = screen(CoinbaseClient(), load_config()["universe_rule"], datetime.now(timezone.utc))
        ours = uni["large"] + uni["mid"]
        yes = [c for c in ours if tradable.get(c)]
        no = [c for c in ours if not tradable.get(c)]
        lines += ["", f"- Large tier on Alpaca: {sum(1 for c in uni['large'] if tradable.get(c))}/{len(uni['large'])}",
                  f"- All eligible on Alpaca: **{len(yes)}/{len(ours)}**",
                  f"- Tradable: {', '.join(yes) or '-'}", f"- NOT on Alpaca: {', '.join(no) or '-'}"]
    except Exception as e:                              # the probe must report, not crash
        lines.append(f"universe screen failed: {e}")

    lines += ["", "## SPY daily bars (benchmark, rule 5)", ""]
    start = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
    code, bars = get(DATA, "/v2/stocks/SPY/bars", {"timeframe": "1Day", "start": start, "feed": "iex"})
    if code == 200 and bars.get("bars"):
        for b in bars["bars"][-5:]:
            lines.append(f"- {b['t'][:10]}: close {b['c']}")
    else:
        lines.append(f"HTTP {code}: {str(bars)[:300]}")

    lines += ["", "## Crypto news (Benzinga via Alpaca)", ""]
    now = datetime.now(timezone.utc)
    for label, s, e in (("last 24h", now - timedelta(days=1), now),
                        ("2020-03-01..03-31", datetime(2020, 3, 1, tzinfo=timezone.utc), datetime(2020, 3, 31, tzinfo=timezone.utc)),
                        ("2023-03-01..03-31", datetime(2023, 3, 1, tzinfo=timezone.utc), datetime(2023, 3, 31, tzinfo=timezone.utc))):
        n, token, sample = 0, None, []
        for _ in range(20):
            p = {"symbols": "BTCUSD,ETHUSD,SOLUSD", "start": s.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "end": e.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 50}
            if token:
                p["page_token"] = token
            code, js = get(DATA, "/v1beta1/news", p)
            if code != 200:
                lines.append(f"- {label}: HTTP {code} {str(js)[:200]}")
                break
            items = js.get("news", [])
            n += len(items)
            sample += [i["headline"] for i in items[:2]]
            token = js.get("next_page_token")
            if not token:
                break
            time.sleep(0.4)
        lines.append(f"- {label}: {n}{'+' if token else ''} articles for BTC/ETH/SOL")
        for h in sample[:2]:
            lines.append(f"  - e.g. “{h[:110]}”")
    return lines


if __name__ == "__main__":
    out = main()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "alpaca_probe.md"), "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
