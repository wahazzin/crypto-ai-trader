"""Alpaca mirror: copies one arm's fills, paper endpoint only, skips coins Alpaca lacks."""
import os
import shutil
import tempfile
import unittest

from crypto_ai.journal import Journal
from mirror import alpaca_mirror as M


class FakeBroker:
    def __init__(self, coins=("BTC-USD", "ETH-USD")):
        self.coins, self.orders, self.pos = set(coins), [], {}

    def tradable(self):
        return self.coins

    def position_qty(self, s):
        return self.pos.get(s, 0.0)

    def order(self, symbol, side, notional=None, qty=None):
        self.orders.append((symbol, side, notional, qty))
        px = 101.0
        if side == "buy":
            self.pos[symbol] = self.pos.get(symbol, 0) + notional / px
        else:
            self.pos[symbol] = self.pos.get(symbol, 0) - qty
        return {"status": "filled", "filled_qty": qty or notional / px, "filled_avg_price": px}


def fill(arm, asset, side, notional, qty=1.0, cause="ai", ts="2026-10-07T10:00:00Z"):
    return {"arm": arm, "asset": asset, "side": side, "notional": notional, "qty": qty, "price": 100.0,
            "cause": cause, "ts": ts}


class TestMirror(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.j = Journal(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_first_run_does_not_replay_history(self):
        self.j.append("orders.jsonl", fill("ai_large", "BTC-USD", "buy", 1000))
        b = FakeBroker()
        self.assertEqual(M.mirror(self.j, b)["new"], 0)
        self.assertEqual(b.orders, [])

    def test_copies_only_its_arm_skips_unlisted_and_measures_price_gap(self):
        b = FakeBroker()
        M.mirror(self.j, b)                                          # start cursor
        self.j.append("orders.jsonl", fill("ai_large", "BTC-USD", "buy", 1000))
        self.j.append("orders.jsonl", fill("s_trend", "ETH-USD", "buy", 500))
        self.j.append("orders.jsonl", fill("ai_large", "QNT-USD", "buy", 800))
        out = M.mirror(self.j, b)
        self.assertEqual(out["new"], 2)
        self.assertEqual(b.orders, [("BTC-USD", "buy", 1000, None)])
        rows = self.j.read("mirror/fills.jsonl")
        self.assertEqual(rows[1]["result"], "unmirrorable")
        self.assertEqual(rows[0]["alpaca_minus_sim_bps"], 100.0)    # paid 1% more than the simulator

    def test_stop_with_earlier_timestamp_is_still_copied_and_closes_fully(self):
        b = FakeBroker()
        M.mirror(self.j, b)
        self.j.append("orders.jsonl", fill("ai_large", "BTC-USD", "buy", 1010, ts="2026-10-07T12:00:00Z"))
        M.mirror(self.j, b)
        self.j.append("orders.jsonl", fill("ai_large", "BTC-USD", "sell", 900, qty=9.0, cause="stop",
                                           ts="2026-10-07T11:55:00Z"))   # candle time, earlier
        M.mirror(self.j, b)
        self.assertEqual(b.orders[-1], ("BTC-USD", "sell", None, 10.0))  # closed everything held
        self.assertAlmostEqual(b.pos["BTC-USD"], 0.0)

    def test_refuses_live_endpoint(self):
        os.environ.setdefault("ALPACA_API_KEY", "x")
        os.environ.setdefault("ALPACA_SECRET_KEY", "y")
        with self.assertRaises(RuntimeError):
            M.AlpacaPaper(base="https://api.alpaca.markets")
