"""Weekly check-in: round-trip P&L, expectancy, scheduling."""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from crypto_ai.analytics import weekly as W
from crypto_ai.journal import Journal
from tests.helpers import test_cfg

CFG = test_cfg()


def o(arm, asset, side, qty, price, fee, ts, cause="ai"):
    return {"arm": arm, "asset": asset, "side": side, "qty": qty, "price": price, "fee_usd": fee,
            "ts": ts, "cause": cause}


class TestWeekly(unittest.TestCase):

    def test_round_trip_includes_all_fees_and_average_cost(self):
        orders = [o("a", "X", "buy", 1, 100, 1, "2026-10-08T00:00:00Z"),
                  o("a", "X", "buy", 1, 120, 1, "2026-10-08T06:00:00Z"),     # avg cost 111 incl fees
                  o("a", "X", "sell", 1, 130, 1, "2026-10-09T00:00:00Z"),    # partial: still open
                  o("a", "X", "sell", 1, 90, 1, "2026-10-10T00:00:00Z")]     # closes
        t = W.closed_trades(orders)
        self.assertEqual(len(t), 1)
        self.assertAlmostEqual(t[0]["pnl_usd"], (130 - 1 - 111) + (90 - 1 - 111))   # -4

    def test_expectancy_not_win_rate(self):
        trades = [{"pnl_usd": 5}, {"pnl_usd": 5}, {"pnl_usd": 5}, {"pnl_usd": -30}]
        s = W.trade_stats(trades)
        self.assertEqual(s["win_rate"], 0.75)
        self.assertAlmostEqual(s["expectancy"], -3.75)      # 75% winners, still losing money

    def test_written_once_per_week_and_not_before_first_full_week(self):
        d = tempfile.mkdtemp()
        j = Journal(d)
        j.save_json("lock.json", {"locked_at": "2026-10-07T06:38:37Z"})
        j.append("equity.jsonl", {"arm": "btc_hold", "ts": "2026-10-07T07:00:00Z", "equity": 10000, "drawdown": 0, "fees_usd": 40})
        j.append("equity.jsonl", {"arm": "btc_hold", "ts": "2026-10-11T18:00:00Z", "equity": 10300, "drawdown": 0, "fees_usd": 40})
        spy = lambda s, e: 0.01
        self.assertIsNone(W.run(d, CFG, datetime(2026, 10, 9, tzinfo=timezone.utc), True, spy))
        path, text = W.run(d, CFG, datetime(2026, 10, 12, 0, 10, tzinfo=timezone.utc), True, spy)
        self.assertTrue(path.endswith("2026-W41.md"))
        self.assertIn("SPY +1.00%", text)
        self.assertIn("| `btc_hold` | +3.00% | +2.00% |", text)                # baseline = starting $10k
        self.assertIn("$40.00", text)                                              # first-cycle fees counted
        self.assertIsNone(W.run(d, CFG, datetime(2026, 10, 12, 0, 15, tzinfo=timezone.utc), True, spy))
        shutil.rmtree(d, ignore_errors=True)
