"""Scanner tests: what wakes the AI, what doesn't, budgets, stops on 5-minute candles, and that
wake-ups never touch the scored files (cycles.jsonl / decisions.jsonl)."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from crypto_ai.agents.llm import MockLLM
from crypto_ai.journal import Journal
from crypto_ai.lock import load_config
from crypto_ai.portfolio.state import Portfolio
from crypto_ai.scanner import find_triggers, run_scan
from tests.test_crypto_ai_pipeline import FakeClient

CFG = load_config()
T0 = datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc)


def snapshot_files(d):
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            with open(p, encoding="utf-8") as fh:
                out[os.path.relpath(p, d)] = fh.read()
    return out


class ScannerBase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.j = Journal(self.dir)
        self.cfg = copy.deepcopy(CFG)

    def scan(self, t, cfg=None):
        return run_scan(self.dir, cfg or self.cfg, FakeClient(t), MockLLM(), now=t, dry_run=True, require_lock=False)

    def cycle_then_heartbeat(self):
        out = self.scan(T0)
        self.assertEqual(out["mode"], "cycle")
        self.scan(T0 + timedelta(minutes=10))          # first scan writes the heartbeat
        return out

    def set_btc_level(self, key, value):
        th = self.j.load_json("theses.json", {})
        th["BTC-USD"][key] = value
        self.j.save_json("theses.json", th)


class TestScannerFlow(ScannerBase):

    def test_due_cycle_runs_the_scheduled_cycle(self):
        out = self.scan(T0)
        self.assertEqual(out["mode"], "cycle")
        self.assertEqual(len(self.j.read("cycles.jsonl")), 1)
        self.assertEqual(self.scan(T0 + timedelta(minutes=5))["mode"], "scan")   # not twice

    def test_not_due_inside_grace_period(self):
        out = self.scan(datetime(2026, 10, 1, 12, 1, tzinfo=timezone.utc))
        self.assertEqual(out["mode"], "scan")
        self.assertEqual(self.j.read("cycles.jsonl"), [])

    def test_quiet_scan_writes_nothing(self):
        self.cycle_then_heartbeat()
        before = snapshot_files(self.dir)
        out = self.scan(T0 + timedelta(minutes=15))
        self.assertEqual(out["status"], "QUIET")
        self.assertEqual(snapshot_files(self.dir), before)

    def test_lock_required_and_nothing_written(self):
        out = run_scan(self.dir, self.cfg, FakeClient(T0), MockLLM(), now=T0, dry_run=True, require_lock=True)
        self.assertEqual(out["status"], "LOCK_MISMATCH")
        self.assertEqual(snapshot_files(self.dir), {})


class TestWakeUps(ScannerBase):

    def test_exit_below_wakes_ai_once_and_keeps_scored_files_clean(self):
        self.cycle_then_heartbeat()
        n_cycles, n_dec = len(self.j.read("cycles.jsonl")), len(self.j.read("decisions.jsonl"))
        self.set_btc_level("exit_below", 10 ** 9)                      # far above price => crossed
        out = self.scan(T0 + timedelta(minutes=20))
        self.assertTrue(out["woke_ai"])
        ev = self.j.read("event_decisions.jsonl")
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["ok"], ev[0].get("errors"))
        self.assertEqual(ev[0]["wake"]["reason"][0]["type"], "EXIT_BELOW_CROSSED")
        self.assertEqual(len(self.j.read("cycles.jsonl")), n_cycles)   # scored files untouched
        self.assertEqual(len(self.j.read("decisions.jsonl")), n_dec)
        self.scan(T0 + timedelta(minutes=60))                          # same level => no refire
        self.assertEqual(len(self.j.read("event_decisions.jsonl")), 1)

    def test_daily_cap_blocks_and_is_logged(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["scanner"]["max_event_calls_per_day"] = 1
        self.scan(T0, cfg); self.scan(T0 + timedelta(minutes=10), cfg)
        self.set_btc_level("exit_below", 10 ** 9)
        self.assertTrue(self.scan(T0 + timedelta(minutes=20), cfg)["woke_ai"])
        self.set_btc_level("exit_below", 10 ** 9 + 1)                  # new level => new trigger
        out = self.scan(T0 + timedelta(minutes=60), cfg)
        self.assertFalse(out["woke_ai"])
        blocked = [e for e in self.j.read("events.jsonl") if e.get("type") == "SCANNER_TRIGGER" and not e["woke_ai"]]
        self.assertEqual(blocked[-1]["blocked_by"], "DAILY_CAP")

    def test_spacing_between_calls(self):
        self.cycle_then_heartbeat()
        self.set_btc_level("exit_below", 10 ** 9)
        self.assertTrue(self.scan(T0 + timedelta(minutes=20))["woke_ai"])
        self.set_btc_level("exit_below", 10 ** 9 + 1)
        self.assertFalse(self.scan(T0 + timedelta(minutes=30))["woke_ai"])   # 10 min later < 30

    def test_quiet_before_scheduled_cycle(self):
        self.cycle_then_heartbeat()
        self.set_btc_level("exit_below", 10 ** 9)
        out = self.scan(datetime(2026, 10, 1, 17, 45, tzinfo=timezone.utc))
        self.assertFalse(out["woke_ai"])
        ev = [e for e in self.j.read("events.jsonl") if e.get("type") == "SCANNER_TRIGGER"]
        self.assertEqual(ev[-1]["blocked_by"], "CYCLE_SOON")


class TestScannerStops(ScannerBase):

    def test_stop_fires_on_5min_candles(self):
        self.cycle_then_heartbeat()
        d = self.j.load_json("arms/ai_pv.json")
        pos = d["positions"]["BTC-USD"]
        pos["avg_cost"] *= 1.05                                        # puts the 5% stop above recent lows
        pos["stop_pct"] = 5.0
        self.j.save_json("arms/ai_pv.json", d)
        out = self.scan(T0 + timedelta(minutes=40))
        stops = [o for o in self.j.read("orders.jsonl") if o["cause"] == "stop" and o["arm"] == "ai_pv"]
        self.assertEqual(len(stops), 1)
        self.assertTrue(stops[0]["cycle_id"].startswith("scan:"))
        self.assertNotIn("BTC-USD", Portfolio.from_dict(self.j.load_json("arms/ai_pv.json")).positions)
        self.assertEqual(out["status"], "ACTIVE")


class TestFindTriggers(unittest.TestCase):

    def mk(self, closes, vols):
        return [{"t": i * 300, "open": c, "high": c, "low": c, "close": c, "volume": v}
                for i, (c, v) in enumerate(zip(closes, vols))]

    def test_big_move_and_volume_spike(self):
        n = 12 * 26
        closes = [100.0] * (n - 12) + [100.0 + i for i in range(12)]
        vols = [1.0] * (n - 12) + [10.0] * 12
        c = {"SOL-USD": self.mk(closes, vols)}
        q = {"SOL-USD": {"mid": 106.0}}
        types = {t["type"] for t in find_triggers(CFG, q, c, Portfolio("ai_pv", 1e4), {})}
        self.assertEqual(types, {"BIG_MOVE_1H", "VOLUME_SPIKE"})

    def test_volume_without_move_is_ignored(self):
        n = 12 * 26
        c = {"SOL-USD": self.mk([100.0] * n, [1.0] * (n - 12) + [10.0] * 12)}
        q = {"SOL-USD": {"mid": 100.2}}
        self.assertEqual(find_triggers(CFG, q, c, Portfolio("ai_pv", 1e4), {}), [])

    def test_levels_only_for_held_coins(self):
        th = {"ETH-USD": {"exit_below": 3000}}
        q = {"ETH-USD": {"mid": 2500.0}}
        self.assertEqual(find_triggers(CFG, q, {}, Portfolio("ai_pv", 1e4), th), [])


if __name__ == "__main__":
    unittest.main()
