"""Phase 14 honesty checks: random-policy replay, calibration, wake-up split."""
import unittest
from datetime import datetime, timedelta, timezone

from crypto_ai.analytics import diagnostics as D
from tests.helpers import test_cfg

CFG = test_cfg()
LARGE = CFG["large"]


def snaps(n, drift):
    """n 6-hourly snapshots; each coin drifts at its own rate (drift[a] per cycle)."""
    out, t0 = [], datetime(2026, 10, 7, 0, tzinfo=timezone.utc)
    for i in range(n):
        assets = {}
        for a in LARGE:
            px = 100.0 * (1 + drift.get(a, 0.0)) ** i
            assets[a] = {"mid": px, "bid": px * 0.9999, "ask": px * 1.0001, "spread_bps": 2.0,
                         "volume_24h_usd": 1e12, "features": {}}
        out.append({"cycle_id": (t0 + timedelta(hours=6 * i)).strftime("%Y-%m-%dT%H:00Z"), "assets": assets,
                    "large": LARGE, "mid": []})
    return out


class TestDiagnostics(unittest.TestCase):

    def test_ai_that_picks_the_only_winner_beats_most_monkeys(self):
        win = LARGE[3]
        S = snaps(40, {win: 0.02, **{a: -0.01 for a in LARGE if a != win}})
        rows = [{"cycle_id": s["cycle_id"], "arm": "ai_large", "ok": True, "view": LARGE,
                 "decisions": ([{"asset": win, "action": "BUY" if i == 0 else "ADD", "target_weight": 0.15 if i == 0 else 0.15}]
                               if i < 2 else [])}
                for i, s in enumerate(S)]
        r = D.random_policy_test(CFG, S, rows, n=60)
        self.assertGreater(r["ai_replay_return"], 0)
        self.assertGreater(r["percentile"], 0.8)

    def test_calibration_and_ladder(self):
        S = snaps(20, {LARGE[0]: 0.01, LARGE[1]: -0.01})
        rows = [{"cycle_id": S[0]["cycle_id"], "scored_assets": LARGE,
                 "outlook": {LARGE[0]: 2, LARGE[1]: -2},
                 "decisions": [{"asset": LARGE[0], "action": "BUY", "confidence": 85, "target_weight": 0.1},
                               {"asset": LARGE[1], "action": "BUY", "confidence": 50, "target_weight": 0.1}]}]
        cal, ladder = D.calibration(rows, S)
        self.assertGreater(cal["80+"]["avg_72h"], 0)
        self.assertLess(cal["<60"]["avg_72h"], 0)
        self.assertEqual(cal["80+"]["hit_72h"], 1.0)
        self.assertGreater(ladder[2][1], 0)
        self.assertLess(ladder[-2][1], 0)

    def test_wakeup_split_by_opening_order(self):
        o = lambda side, cause, ts, px: {"arm": "ai_large", "asset": "X", "side": side, "qty": 1, "price": px,
                                         "fee_usd": 0, "ts": ts, "cause": cause}
        orders = [o("buy", "ai_event", "2026-10-07T01:00:00Z", 100), o("sell", "ai", "2026-10-08T00:00:00Z", 110),
                  o("buy", "ai", "2026-10-09T00:00:00Z", 100), o("sell", "stop", "2026-10-10T00:00:00Z", 90)]
        s = D.wakeup_split(orders, "ai_large")
        self.assertEqual(s["wake-up"], {"closed": 1, "pnl_usd": 10})
        self.assertEqual(s["scheduled"], {"closed": 1, "pnl_usd": -10})
