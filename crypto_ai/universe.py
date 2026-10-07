"""
universe.py -- which coins the bot may trade, chosen by a written RULE, never by hand.

WHY: picking coins by eye means picking the ones that already went up (survivorship +
look-ahead bias). The rule only uses facts that say nothing about future returns:

  eligible = Coinbase USD pair, online, not trading-disabled
             AND not a stablecoin / wrapped-or-staked copy / memecoin
             AND >= min_history_days of daily candles
  ranked by 30-day USD volume (liquidity => believable paper fills, harder to manipulate)
  LARGE = top `large_n`
  MID   = next ranks up to `mid_max_rank`, only if average daily volume >= `mid_min_daily_usd`

REFRESH: once per calendar month (first cycle of the month). The screen result is saved in
universe.json and every refresh is logged to universe_history.jsonl. A coin that drops out stays
in the market data while any arm still holds it (so it can be sold), but no arm may BUY/ADD it.

Two modes (experiment.json -> universe_rule.mode):
  "screen": the real thing, described above
  "fixed":  use experiment.json -> universe_fixed (tests and offline dry runs only)
"""
from crypto_ai.journal import iso
from crypto_ai.market_data.coinbase import DataFault


def screen(client, rule, now):
    """Returns {"asof_month", "screened_at", "large", "mid", "ranked": [...]}. Raises DataFault."""
    excl = {b: k for k, names in rule["exclude"].items() for b in names}
    rows = []
    for p in client.products():
        if p.get("quote_currency") != "USD" or p.get("status") != "online" or p.get("trading_disabled"):
            continue
        base = p["base_currency"]
        if base in excl:
            continue
        try:
            st = client.stats(p["id"])
        except DataFault:
            continue
        rows.append({"product": p["id"], "vol30_base": st["volume_30day"], "last": st["last"]})
    for r in rows:
        r["avg_daily_usd"] = r["vol30_base"] * r["last"] / 30
    rows.sort(key=lambda r: -r["avg_daily_usd"])
    ranked = []
    for r in rows:                                   # history check only for the top of the list
        if len(ranked) >= rule["mid_max_rank"]:
            break
        try:
            days = len(client.candles(r["product"], 86400))
        except DataFault:
            continue
        if days < rule["min_history_days"]:
            continue
        ranked.append({"rank": len(ranked) + 1, "product": r["product"],
                       "avg_daily_usd_M": round(r["avg_daily_usd"] / 1e6, 2), "history_days": days})
    if len(ranked) < rule["large_n"]:
        raise DataFault(f"universe screen found only {len(ranked)} eligible coins")
    large = [r["product"] for r in ranked[:rule["large_n"]]]
    mid = [r["product"] for r in ranked[rule["large_n"]:]
           if r["avg_daily_usd_M"] * 1e6 >= rule["mid_min_daily_usd"]]
    return {"asof_month": now.strftime("%Y-%m"), "screened_at": iso(now), "mode": "screen",
            "large": large, "mid": mid, "ranked": ranked}


def current(j, cfg, client, now):
    """The universe for this cycle, refreshing it at most once per month. Returns (universe, event|None).
    If a refresh fails, the previous month's universe is kept (and the failure reported)."""
    rule = cfg["universe_rule"]
    u = j.load_json("universe.json")
    if rule["mode"] == "fixed":
        fixed = {"asof_month": "fixed", "mode": "fixed", "large": rule["fixed_large"],
                 "mid": rule.get("fixed_mid", []), "ranked": []}
        if u != fixed:
            j.save_json("universe.json", fixed)
        return fixed, None
    if u and u.get("asof_month") == now.strftime("%Y-%m"):
        return u, None
    try:
        new = screen(client, rule, now)
    except DataFault as e:
        if u:
            return u, {"type": "UNIVERSE_REFRESH_FAILED", "error": str(e), "kept": u["asof_month"]}
        raise
    j.save_json("universe.json", new)
    j.append("universe_history.jsonl", new)
    ev = {"type": "UNIVERSE_REFRESHED", "asof_month": new["asof_month"], "large": new["large"], "mid": new["mid"]}
    if u:
        ev["added"] = sorted(set(new["large"] + new["mid"]) - set(u["large"] + u["mid"]))
        ev["removed"] = sorted(set(u["large"] + u["mid"]) - set(new["large"] + new["mid"]))
    return new, ev


def cycle_config(cfg, uni, held):
    """A per-cycle copy of the config. `universe` = every coin we need data for this cycle
    (eligible + anything an arm still holds); `large`, `mid`, `eligible` drive caps and rules."""
    c = dict(cfg)
    eligible = list(dict.fromkeys(uni["large"] + uni["mid"]))
    c["large"], c["mid"], c["eligible"] = list(uni["large"]), list(uni["mid"]), eligible
    c["universe"] = eligible + sorted(set(held) - set(eligible))
    return c
