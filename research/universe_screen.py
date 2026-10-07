"""
universe_screen.py -- which coins are even ELIGIBLE to trade? A rule, not a human pick.

WHY A RULE: if a person picks coins by looking at charts, they pick the ones that already went
up. That's survivorship + look-ahead bias, and it makes any test look better than reality.
So eligibility only uses things that say nothing about future returns:

  1. Tradeable on Coinbase vs USD, not disabled
  2. Not a stablecoin, wrapped/staked copy, or memecoin (memecoins = project 3)
  3. Enough history (>= 300 daily candles) to compute features honestly
  4. Liquid enough that paper fills are believable: 30-day USD volume and live spread

Past returns are deliberately NOT shown or used.

Output: research/out/universe_screen.csv and .md, tiered:
  LARGE = top 10 eligible by 30d USD volume
  MID   = ranks 11-30 with >= $5M/day average volume (the "funds skip it, a small account
          doesn't" tier from the project description)

Usage:  python -m research.universe_screen
"""
import csv
import os
import time

from crypto_ai.market_data.coinbase import CoinbaseClient, DataFault

STABLE = {"USDT", "USDC", "DAI", "PYUSD", "EURC", "GUSD", "PAX", "USDP", "USDS", "FDUSD", "TUSD",
          "BUSD", "LUSD", "GYEN", "RLUSD", "USD1", "EUR", "GBP", "PAXG", "XAUT"}  # incl. gold-backed
WRAPPED = {"WBTC", "CBBTC", "CBETH", "WSTETH", "RETH", "STETH", "MSOL", "JITOSOL", "LSETH", "WETH",
           "WAXL", "TBTC", "LBTC"}
MEME = {"DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "MOG", "TRUMP", "POPCAT", "PENGU", "BRETT",
        "MEW", "TURBO", "FARTCOIN", "SPX", "GIGA", "PNUT", "MOODENG", "NEIRO", "DEGEN", "TOSHI",
        "MELANIA", "WOJAK", "BOME", "MOTHER", "PONKE"}

MIN_DAYS = 300
MID_MIN_DAILY_USD = 5e6
OUT = os.path.join(os.path.dirname(__file__), "out")


def main():
    c = CoinbaseClient()
    products = c._get("/products")
    usd = [p for p in products if p.get("quote_currency") == "USD" and p.get("status") == "online"
           and not p.get("trading_disabled")]
    rows = []
    for p in usd:
        base = p["base_currency"]
        excluded = ("stablecoin" if base in STABLE else "wrapped/staked" if base in WRAPPED
                    else "memecoin (project 3)" if base in MEME else "")
        r = {"product": p["id"], "base": base, "excluded": excluded}
        if not excluded:
            try:
                st = c._get(f"/products/{p['id']}/stats")
                tk = c.ticker(p["id"])
                days = len(c.candles(p["id"], 86400))
                mid = (tk["bid"] + tk["ask"]) / 2
                r.update({"vol30d_usd_M": round(float(st.get("volume_30day") or 0) * mid / 1e6, 1),
                          "avg_daily_usd_M": round(float(st.get("volume_30day") or 0) * mid / 30 / 1e6, 2),
                          "spread_bps": round((tk["ask"] - tk["bid"]) / mid * 1e4, 2),
                          "history_days": days})
                if days < MIN_DAYS:
                    r["excluded"] = f"history < {MIN_DAYS}d"
            except DataFault as e:
                r["excluded"] = f"data error: {e}"
        rows.append(r)
        time.sleep(0.05)

    ok = sorted([r for r in rows if not r["excluded"]], key=lambda r: -r["vol30d_usd_M"])
    for i, r in enumerate(ok, 1):
        r["rank"] = i
        r["tier"] = ("LARGE" if i <= 10 else
                     "MID" if i <= 30 and r["avg_daily_usd_M"] * 1e6 >= MID_MIN_DAILY_USD else "")
    os.makedirs(OUT, exist_ok=True)
    cols = ["rank", "tier", "product", "avg_daily_usd_M", "vol30d_usd_M", "spread_bps", "history_days", "excluded"]
    with open(os.path.join(OUT, "universe_screen.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in ok + [r for r in rows if r["excluded"]]:
            w.writerow(r)
    with open(os.path.join(OUT, "universe_screen.md"), "w") as f:
        f.write(f"# Universe screen ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})\n\n")
        f.write(f"USD products online: {len(usd)}; eligible: {len(ok)}\n\n")
        f.write("| Rank | Tier | Coin | Avg daily vol ($M) | Spread (bps) | History (days) |\n|---|---|---|---|---|---|\n")
        for r in ok[:40]:
            f.write(f"| {r['rank']} | {r['tier']} | {r['product']} | {r['avg_daily_usd_M']} | {r['spread_bps']} | {r['history_days']} |\n")
        ex = {}
        for r in rows:
            if r["excluded"]:
                ex.setdefault(r["excluded"].split(":")[0], []).append(r["base"])
        f.write("\n## Excluded\n\n")
        for k, v in sorted(ex.items()):
            f.write(f"- **{k}** ({len(v)}): {', '.join(sorted(v)[:40])}{' …' if len(v) > 40 else ''}\n")
    print(open(os.path.join(OUT, "universe_screen.md")).read())


if __name__ == "__main__":
    main()
