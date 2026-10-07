"""
weekly.py -- the weekly check-in (project rule 2), written automatically every Monday.

For every portfolio, over the last 7 days AND since the start:
  * total trades (fills) and closed round trips
  * win rate, average win $ vs average loss $, expectancy $ per closed trade (rule 6: never win rate alone)
  * return %, current drawdown %, max drawdown %, fees paid
  * vs BTC hold and vs SPY over the same window (rule 5). SPY comes from Alpaca's daily bars.

A "closed trade" = a position from first buy until it is fully sold. Its P&L includes every fee on
the way in and out. Cost basis is average cost (adds raise it, partial sells realise P&L at it).

Interim banner always on top: a week of results is noise and is never a verdict (PREREGISTRATION §10).

Usage:
  python -m crypto_ai.analytics.weekly --state-dir DIR            # report for the last full week
  python -m crypto_ai.analytics.weekly --state-dir DIR --if-due   # only if this week's isn't written yet
"""
import argparse
import os
from datetime import datetime, timedelta, timezone

import requests

from crypto_ai.journal import Journal, iso, now_utc, parse_iso
from crypto_ai.lock import load_config

BANNER = "INTERIM — INFORMATIONAL ONLY. A week of results is noise, not evidence of edge."


def closed_trades(orders):
    """Average-cost round trips per (arm, asset). Returns list of {arm, asset, open_ts, close_ts, pnl_usd}."""
    book, out = {}, []
    for o in sorted(orders, key=lambda r: r["ts"]):
        k = (o["arm"], o["asset"])
        p = book.setdefault(k, {"qty": 0.0, "cost": 0.0, "pnl": 0.0, "open": None})
        if o["side"] == "buy":
            if p["qty"] <= 1e-12:
                p.update(qty=0.0, cost=0.0, pnl=0.0, open=o["ts"])
            p["qty"] += o["qty"]
            p["cost"] += o["qty"] * o["price"] + o["fee_usd"]
        else:
            if p["qty"] <= 1e-12:
                continue
            q = min(o["qty"], p["qty"])
            basis = p["cost"] * q / p["qty"]
            p["pnl"] += q * o["price"] - o["fee_usd"] - basis
            p["cost"] -= basis
            p["qty"] -= q
            if p["qty"] <= 1e-9 * max(1.0, q):
                out.append({"arm": o["arm"], "asset": o["asset"], "open_ts": p["open"], "close_ts": o["ts"],
                            "pnl_usd": p["pnl"], "exit": o["cause"]})
                p.update(qty=0.0, cost=0.0, pnl=0.0, open=None)
    return out


def trade_stats(trades):
    wins = [t["pnl_usd"] for t in trades if t["pnl_usd"] > 0]
    losses = [t["pnl_usd"] for t in trades if t["pnl_usd"] <= 0]
    n = len(trades)
    if not n:
        return {"closed": 0, "win_rate": None, "avg_win": None, "avg_loss": None, "expectancy": None}
    wr = len(wins) / n
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    return {"closed": n, "win_rate": wr, "avg_win": aw, "avg_loss": al, "expectancy": wr * aw + (1 - wr) * al}


def equity_window(eq_rows, arm, start, end, initial):
    """Return over [start, end]. Baseline = the last equity row BEFORE the window (or the starting
    capital if there is none), so fees and moves at the very first cycle are counted."""
    rows = sorted((r for r in eq_rows if r["arm"] == arm), key=lambda r: r["ts"])
    inside = [r for r in rows if start <= parse_iso(r["ts"]) <= end]
    if not inside:
        return None
    before = [r for r in rows if parse_iso(r["ts"]) < start]
    base = before[-1] if before else {"equity": initial, "fees_usd": 0.0}
    vals = [base["equity"]] + [r["equity"] for r in inside]
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return {"start": vals[0], "end": vals[-1], "ret": vals[-1] / vals[0] - 1, "max_dd": mdd,
            "dd_now": inside[-1].get("drawdown"), "fees": inside[-1].get("fees_usd", 0.0) - base.get("fees_usd", 0.0)}


def spy_return(start, end):
    """SPY close-to-close return over [start, end] from Alpaca (IEX feed). None if unavailable."""
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not (k and s):
        return None
    try:
        r = requests.get("https://data.alpaca.markets/v2/stocks/SPY/bars",
                         headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s},
                         params={"timeframe": "1Day", "feed": "iex",
                                 "start": (start - timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z"),
                                 "end": end.strftime("%Y-%m-%dT23:59:59Z")}, timeout=30)
        bars = r.json().get("bars") or []
    except (requests.RequestException, ValueError):
        return None
    before = [b for b in bars if b["t"][:10] <= start.strftime("%Y-%m-%d")]
    after = [b for b in bars if b["t"][:10] <= end.strftime("%Y-%m-%d")]
    if not before or not after:
        return None
    return after[-1]["c"] / before[-1]["c"] - 1


def _p(x, d=2):
    return "—" if x is None else f"{100 * x:+.{d}f}%"


def _d(x):
    return "—" if x is None else f"${x:+,.2f}"


def build(state_dir, cfg, week_end, spy_fn=spy_return):
    j = Journal(state_dir)
    lock = j.load_json("lock.json")
    start_all = parse_iso(lock["locked_at"]) if lock else week_end - timedelta(days=7)
    week_start = max(week_end - timedelta(days=7), start_all)
    eq, orders = j.read("equity.jsonl"), j.read("orders.jsonl")
    trades = closed_trades(orders)
    init = cfg["capital"]["initial_cash_usd"]
    week_label = (week_end - timedelta(days=1)).strftime("%G-W%V")
    lines = [f"# Weekly check-in {week_label}", "", f"> {BANNER}", "",
             f"Window: {iso(week_start)} → {iso(week_end)}. Since start: {iso(start_all)}.", ""]
    for label, s in (("This week", week_start), ("Since start", start_all)):
        spy = spy_fn(s, week_end)
        btc = equity_window(eq, "btc_hold", s, week_end, init)
        lines += [f"## {label}", "",
                  f"Benchmarks: **SPY {_p(spy)}** · **BTC hold {_p(btc and btc['ret'])}** (same window)", "",
                  "| Portfolio | Return | vs SPY | vs BTC | Drawdown now | Max DD | Fills | Closed trades | Win rate | Avg win | Avg loss | Expectancy/trade | Fees |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm in cfg["arms"]:
            w = equity_window(eq, arm, s, week_end, init)
            if not w:
                continue
            fills = sum(1 for o in orders if o["arm"] == arm and s <= parse_iso(o["ts"]) <= week_end)
            st = trade_stats([t for t in trades if t["arm"] == arm and s <= parse_iso(t["close_ts"]) <= week_end])
            vs_spy = None if spy is None else w["ret"] - spy
            vs_btc = None if not btc else w["ret"] - btc["ret"]
            lines.append(f"| `{arm}` | {_p(w['ret'])} | {_p(vs_spy)} | {_p(vs_btc)} | {_p(w['dd_now'])} | {_p(w['max_dd'])} | "
                         f"{fills} | {st['closed']} | {_p(st['win_rate'], 0) if st['win_rate'] is not None else '—'} | "
                         f"{_d(st['avg_win'])} | {_d(st['avg_loss'])} | {_d(st['expectancy'])} | ${w['fees']:,.2f} |")
        lines.append("")
    cyc = [c for c in j.read("cycles.jsonl") if week_start <= parse_iso(c["started_at"]) <= week_end]
    ok = sum(c["status"] in ("OK", "OK_AI_FAULT") for c in cyc)
    faults = sum(c["status"] == "OK_AI_FAULT" for c in cyc)
    ev = [e for e in j.read("event_decisions.jsonl") if week_start <= parse_iso(e["ts"]) <= week_end]
    toks = sum((c.get("tokens_in") or 0) + (c.get("tokens_out") or 0) for c in cyc)
    expected = int((week_end - week_start).total_seconds() // (6 * 3600))
    lines += ["## Health", "",
              f"- Scheduled cycles completed: **{ok} / ~{expected}** expected (AI faults: {faults})",
              f"- AI wake-ups: {len(ev)} ({sum(1 for e in ev if e.get('ok'))} answered OK)",
              f"- AI tokens used by cycles: {toks:,}", "",
              "Expectancy = win rate × avg win + loss rate × avg loss, per closed trade, after all fees "
              "(rule 6). Hold portfolios rarely close trades, so their columns stay empty.", ""]
    return week_label, "\n".join(lines)


def run(state_dir, cfg, now, if_due=False, spy_fn=spy_return):
    """Writes reports/weekly/<week>.md for the last COMPLETED week (Mon 00:00 UTC boundary)."""
    j = Journal(state_dir)
    lock = j.load_json("lock.json")
    if lock is None and if_due:
        return None
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    if lock and monday <= parse_iso(lock["locked_at"]):
        return None                                  # no full week since the start yet
    label = (monday - timedelta(days=1)).strftime("%G-W%V")
    path = f"reports/weekly/{label}.md"
    if if_due and os.path.exists(j.path(path)):
        return None
    _, text = build(state_dir, cfg, monday, spy_fn)
    os.makedirs(os.path.dirname(j.path(path)), exist_ok=True)
    with open(j.path(path), "w", encoding="utf-8") as f:
        f.write(text)
    return path, text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--if-due", action="store_true")
    ap.add_argument("--preview", metavar="OUT_FILE", help="report from the start until NOW, written to OUT_FILE")
    a = ap.parse_args()
    if a.preview:
        _, text = build(a.state_dir, load_config(), now_utc())
        os.makedirs(os.path.dirname(a.preview) or ".", exist_ok=True)
        with open(a.preview, "w", encoding="utf-8") as fh:
            fh.write(text.replace("# Weekly check-in", "# Weekly check-in PREVIEW (partial week)", 1))
        print(text)
        raise SystemExit(0)
    out = run(a.state_dir, load_config(), now_utc(), a.if_due)
    if out:
        print(out[1])
        try:
            from crypto_ai.notify import alert
            alert(f"Weekly check-in {out[0]} written to the crypto-ai-data branch.")
        except Exception:
            pass
