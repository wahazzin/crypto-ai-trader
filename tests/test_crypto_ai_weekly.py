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


class TestSpyWindow(unittest.TestCase):
    def test_start_before_the_session_uses_previous_close(self):
        from crypto_ai.analytics import weekly as W
        bars = [{"t": "2026-10-06T04:00:00Z", "c": 779.10}, {"t": "2026-10-07T04:00:00Z", "c": 777.15},
                {"t": "2026-10-09T04:00:00Z", "c": 778.51}]
        r = W._spy_from_bars(bars, datetime(2026, 10, 7, 6, 38, tzinfo=timezone.utc),
                             datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertAlmostEqual(r, 778.51 / 779.10 - 1)        # was 778.51 / 777.15 - 1 (skipped 10-07)
        r2 = W._spy_from_bars(bars, datetime(2026, 10, 7, 22, 0, tzinfo=timezone.utc),
                              datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertAlmostEqual(r2, 778.51 / 777.15 - 1)       # start after that day's close



class TestHealthAndDrawdown(unittest.TestCase):
    """2026-10-26: health line counted every provider's tokens against Groq's cap; Max DD since start could be
    smaller than DD now (s_breakout W43: DD now -9.42% vs Max DD -9.09%)."""

    def test_provider_usage_splits_groq_and_cloudflare(self):
        rows = [{"provider": "groq", "ts": "2026-10-20T00:00:00Z", "tokens_in": 6000, "tokens_out": 2000},
                {"provider": "cloudflare", "ts": "2026-10-20T06:00:00Z", "tokens_in": 7397, "tokens_out": 1403},
                {"provider": "cloudflare", "ts": "2026-10-21T06:00:00Z", "tokens_in": 1000, "tokens_out": 0}]
        u = W.provider_usage(rows)
        self.assertEqual(u["calls"], {"groq": 1, "cloudflare": 2})
        self.assertEqual(u["groq_tokens"], 8000)
        self.assertAlmostEqual(u["cf_neurons_by_day"]["2026-10-20"], 331, delta=1)   # matches the real probe

    def test_since_start_max_dd_includes_engine_drawdown(self):
        eq = [{"arm": "a", "ts": "2026-10-07T07:00:00Z", "equity": 10000, "drawdown": 0.0},
              {"arm": "a", "ts": "2026-10-08T07:00:00Z", "equity": 9100, "drawdown": -0.0942}]
        w = W.equity_window(eq, "a", datetime(2026, 10, 7, tzinfo=timezone.utc),
                            datetime(2026, 10, 9, tzinfo=timezone.utc), 10000)
        self.assertLessEqual(w["max_dd"], w["dd_now"])
