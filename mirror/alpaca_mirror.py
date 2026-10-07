"""
alpaca_mirror.py -- copies the AI's simulated trades onto the Alpaca PAPER account.

WHY: our simulator is the scorekeeper (it's stricter than Alpaca's paper fills, ROADMAP C5). The
mirror exists to rehearse the real order path (real API, real rejections, real fill prices) and to
MEASURE how far our simulated fills are from a broker's, coin by coin.

HOW (copy orders, not weights, so nothing drifts or churns):
  * reads new fills of ONE arm (default ai_large) from orders.jsonl since the last mirrored one
  * same dollar size on Alpaca; full exits close the Alpaca position
  * coins Alpaca doesn't list are skipped and counted ("unmirrorable")
  * logs simulated vs Alpaca fill price for every copied order -> mirror/fills.jsonl

SAFETY:
  * PAPER ONLY: the base URL is hard-coded to paper-api.alpaca.markets and checked before any call.
  * Lives OUTSIDE the crypto_ai package on purpose: the experiment package stays order-free
    (a test enforces that). This module can only ever touch the paper account.
  * Never logs keys or the account number.

Usage: python -m mirror.alpaca_mirror --state-dir DIR [--arm ai_large]
"""
import argparse
import os
import time

import requests

PAPER = "https://paper-api.alpaca.markets"
MIN_NOTIONAL = 10.0


class AlpacaPaper:
    def __init__(self, session=None, base=PAPER):
        if base != PAPER:
            raise RuntimeError("mirror refuses any endpoint except the PAPER API")
        self.base = base
        self.s = session or requests.Session()
        self.h = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                  "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}

    def _req(self, method, path, **kw):
        r = self.s.request(method, self.base + path, headers=self.h, timeout=30, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {"text": r.text[:300]}
        return r.status_code, body

    def tradable(self):
        code, assets = self._req("GET", "/v2/assets", params={"asset_class": "crypto", "status": "active"})
        if code != 200:
            raise RuntimeError(f"assets HTTP {code}")
        return {a["symbol"].replace("/", "-") for a in assets if a.get("tradable")}

    def position_qty(self, symbol):
        code, p = self._req("GET", f"/v2/positions/{symbol.replace('-', '')}")
        return float(p.get("qty", 0)) if code == 200 else 0.0

    def order(self, symbol, side, notional=None, qty=None):
        body = {"symbol": symbol.replace("-", "/"), "side": side, "type": "market", "time_in_force": "gtc"}
        if qty is not None:
            body["qty"] = f"{qty:.9f}".rstrip("0").rstrip(".")
        else:
            body["notional"] = f"{notional:.2f}"
        code, o = self._req("POST", "/v2/orders", json=body)
        if code not in (200, 201):
            return {"status": "rejected", "http": code, "error": str(o)[:300]}
        for _ in range(6):                                   # market crypto orders fill in ~1 s
            if o.get("status") in ("filled", "canceled", "rejected", "expired"):
                break
            time.sleep(1)
            _, o = self._req("GET", f"/v2/orders/{o['id']}")
        return {"status": o.get("status"), "filled_qty": float(o.get("filled_qty") or 0),
                "filled_avg_price": float(o["filled_avg_price"]) if o.get("filled_avg_price") else None}


def mirror(j, broker, arm="ai_large"):
    """Copy new fills of `arm`. Returns a summary dict. `j` is a crypto_ai Journal on the state dir."""
    st = j.load_json("mirror/state.json", {"cursor": None, "copied": 0, "skipped": 0, "rejected": 0})
    rows = j.read("orders.jsonl")
    if st["cursor"] is None:
        # first run: start from here; don't replay history the Alpaca account never saw
        st["cursor"] = len(rows)
        j.save_json("mirror/state.json", st)
        return {"new": 0, "note": f"mirror started after order row {len(rows)}"}
    # cursor = number of orders.jsonl rows already looked at. (Not a timestamp: stop fills carry the
    # candle's time, which can be EARLIER than fills already mirrored.)
    new = [o for o in rows[st["cursor"]:] if o["arm"] == arm]
    if not new:
        st["cursor"] = len(rows)
        j.save_json("mirror/state.json", st)
        return {"new": 0}
    ok_syms = broker.tradable()
    done = []
    for o in new:
        row = {"ts": o["ts"], "arm": arm, "asset": o["asset"], "side": o["side"], "cause": o["cause"],
               "sim_price": o["price"], "sim_notional": o["notional"]}
        if o["asset"] not in ok_syms:
            row["result"] = "unmirrorable"
            st["skipped"] += 1
        elif o["side"] == "buy":
            if o["notional"] < MIN_NOTIONAL:
                row["result"] = "too_small"
            else:
                row.update(broker.order(o["asset"], "buy", notional=o["notional"]))
        else:
            held = broker.position_qty(o["asset"])
            q = held if o.get("cause") in ("stop", "breaker") or o["qty"] >= held * 0.999 else min(o["qty"], held)
            row.update(broker.order(o["asset"], "sell", qty=q) if q > 0 else {"status": "nothing_held"})
        if row.get("filled_avg_price") and o["price"]:
            sign = 1 if o["side"] == "buy" else -1
            row["alpaca_minus_sim_bps"] = round(sign * (row["filled_avg_price"] / o["price"] - 1) * 1e4, 2)
        if row.get("status") == "rejected":
            st["rejected"] += 1
        elif row.get("status") == "filled":
            st["copied"] += 1
        j.append("mirror/fills.jsonl", row)
        done.append(row)
    st["cursor"] = len(rows)
    j.save_json("mirror/state.json", st)
    return {"new": len(done), "rows": done}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from crypto_ai.journal import Journal
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--arm", default="ai_large")
    a = ap.parse_args()
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")):
        print("mirror: no Alpaca keys, skipping")
        raise SystemExit(0)
    try:
        out = mirror(Journal(a.state_dir), AlpacaPaper(), a.arm)
    except (RuntimeError, requests.RequestException) as e:
        print(f"mirror: skipped this tick ({e})")          # the mirror must never break the bot
        raise SystemExit(0)
    print({k: v for k, v in out.items() if k != "rows"})
    for r in out.get("rows", []):
        print("  ", r)
