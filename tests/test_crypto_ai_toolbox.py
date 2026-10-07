"""Toolbox strategies, the universe rule, and the two-AI lineup."""
import copy
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from crypto_ai import universe as U
from crypto_ai.agents.llm import MockLLM
from crypto_ai.journal import Journal
from crypto_ai.lock import create_lock
from crypto_ai.portfolio.state import Portfolio
from crypto_ai.risk.engine import Proposal, evaluate
from crypto_ai.runner import ai_view, run_cycle
from crypto_ai.strategies import toolbox as T
from tests.helpers import test_cfg
from tests.test_crypto_ai_pipeline import FakeClient

CFG = test_cfg()
SP = CFG["strategies"]


def days(closes, vols=None, hi=None, lo=None):
    vols = vols or [1.0] * len(closes)
    return [{"t": i * 86400, "open": c, "close": c, "high": (hi or {}).get(i, c), "low": (lo or {}).get(i, c),
             "volume": v} for i, (c, v) in enumerate(zip(closes, vols))]


class TestSignals(unittest.TestCase):

    def test_trend_on_in_rising_market_off_in_falling(self):
        self.assertTrue(T.trend_signal(days([100 + i for i in range(80)]), SP["trend"])["on"])
        self.assertFalse(T.trend_signal(days([200 - i for i in range(80)]), SP["trend"])["on"])

    def test_trend_needs_history(self):
        self.assertFalse(T.trend_signal(days([100] * 30), SP["trend"])["on"])

    def test_breakout_needs_volume(self):
        c = [100.0] * 40 + [110.0]
        self.assertFalse(T.breakout_signal(days(c), SP["breakout"])["on"])               # no volume
        self.assertTrue(T.breakout_signal(days(c, [1.0] * 40 + [3.0]), SP["breakout"])["on"])

    def test_breakout_exits_on_10_day_low(self):
        c = [100.0] * 40 + [110.0] + [111.0] * 5 + [90.0]
        v = [1.0] * 40 + [3.0] + [1.0] * 6
        s = T.breakout_signal(days(c, v), SP["breakout"])
        self.assertFalse(s["on"])

    def test_dip_in_uptrend_then_exit_on_recovery(self):
        up = [100 + i for i in range(70)]
        dip = up + [up[-1] * 0.95, up[-1] * 0.90]                  # -10% over 2 days, trend intact
        self.assertTrue(T.dip_signal(days(dip), SP["dip"])["on"])
        rec = dip + [up[-1] * 1.02]                                # back above SMA10
        self.assertFalse(T.dip_signal(days(rec), SP["dip"])["on"])

    def test_no_dip_signal_in_downtrend(self):
        down = [200 - i for i in range(70)]
        self.assertFalse(T.dip_signal(days(down + [down[-1] * 0.88]), SP["dip"])["on"])

    def test_rotation_picks_top3_positive_only(self):
        d = {"A": days([100 + 2 * i for i in range(40)]), "B": days([100 + i for i in range(40)]),
             "C": days([100 + 0.5 * i for i in range(40)]), "D": days([100 + 3 * i for i in range(40)]),
             "E": days([100 - i for i in range(40)])}
        r = T.rotation_ranks(d, list(d), SP["rotation"])
        self.assertEqual({a for a, x in r.items() if x["pick"]}, {"D", "A", "B"})
        d2 = {"E": d["E"]}
        self.assertFalse(T.rotation_ranks(d2, ["E"], SP["rotation"])["E"]["pick"])  # negative never picked

    def test_mid_candidates_prefers_strong_signals_and_keeps_held(self):
        def sig(trend=False, br=False, dip=False, pick=False, rank=9):
            return {"trend": {"on": trend}, "breakout": {"on": br}, "dip": {"on": dip},
                    "rotation": {"pick": pick, "rank": rank}}
        s = {"M1": sig(trend=True), "M2": sig(br=True), "M3": sig(), "M4": sig(dip=True, trend=True), "M5": sig(trend=True)}
        self.assertEqual(T.mid_candidates(s, list(s), [], 2), ["M4", "M2"])
        self.assertEqual(T.mid_candidates(s, list(s), ["M3"], 1)[0], "M3")      # held always visible


class TestRiskForMid(unittest.TestCase):

    def snap(self):
        return {"assets": {a: {"mid": 100.0, "bid": 99.99, "ask": 100.01, "spread_bps": 2.0,
                               "volume_24h_usd": 1e12, "features": {}} for a in CFG["universe"] + ["OLD-USD"]}}

    def test_mid_coin_capped_at_10pct(self):
        cfg = dict(CFG, risk=dict(CFG["risk"], max_turnover_24h=1.0))
        d = evaluate([Proposal("x", "UNI-USD", "BUY", 0.15, 5, "t")], Portfolio("x", 1e4), self.snap(), cfg,
                     datetime(2026, 10, 1, tzinfo=timezone.utc))[0]
        self.assertAlmostEqual(d["final_weight"], 0.10, places=3)
        self.assertIn("R1_ASSET_CAP", d["codes"])

    def test_cannot_buy_coin_that_left_the_universe(self):
        d = evaluate([Proposal("x", "OLD-USD", "BUY", 0.05, None, "t")], Portfolio("x", 1e4), self.snap(), CFG,
                     datetime(2026, 10, 1, tzinfo=timezone.utc))[0]
        self.assertEqual(d["codes"], ["R15_NOT_ELIGIBLE"])


class FakeExchange(FakeClient):
    """FakeClient plus the listing endpoints the universe screen uses."""
    LIST = [("BTC", 900), ("ETH", 800), ("USDT", 5000), ("DOGE", 700), ("SOL", 600), ("NEW", 650),
            ("XRP", 500), ("ADA", 400), ("LINK", 300), ("AVAX", 200), ("LTC", 150), ("UNI", 140),
            ("NEAR", 130), ("SUI", 120), ("THIN", 0.0001)]

    def __init__(self, now):
        super().__init__(now)
        for b, _ in self.LIST:
            self.base.setdefault(f"{b}-USD", 50.0)

    def products(self):
        return [{"id": f"{b}-USD", "base_currency": b, "quote_currency": "USD", "status": "online",
                 "trading_disabled": False} for b, _ in self.LIST]

    def stats(self, p):
        v = dict(self.LIST)[p.split("-")[0]]
        return {"volume_30day": v * 1e6, "last": 1.0}

    def candles(self, p, g):
        rows = super().candles(p, g)
        return rows[-20:] if p == "NEW-USD" and g == 86400 else rows      # NEW: too little history


class TestUniverseRule(unittest.TestCase):

    def setUp(self):
        self.cfg = copy.deepcopy(CFG)
        self.cfg["universe_rule"]["mode"] = "screen"
        self.now = datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc)

    def test_rule_excludes_stables_memes_short_history_and_thin(self):
        u = U.screen(FakeExchange(self.now), self.cfg["universe_rule"], self.now)
        allc = u["large"] + u["mid"]
        for bad in ("USDT-USD", "DOGE-USD", "NEW-USD", "THIN-USD"):
            self.assertNotIn(bad, allc)
        self.assertEqual(u["large"][:3], ["BTC-USD", "ETH-USD", "SOL-USD"])
        self.assertEqual(len(u["large"]), 10)

    def test_refresh_once_per_month(self):
        d = tempfile.mkdtemp()
        j = Journal(d)
        u1, ev = U.current(j, self.cfg, FakeExchange(self.now), self.now)
        self.assertEqual(ev["type"], "UNIVERSE_REFRESHED")
        u2, ev2 = U.current(j, self.cfg, FakeExchange(self.now), self.now + timedelta(days=5))
        self.assertIsNone(ev2)
        u3, ev3 = U.current(j, self.cfg, FakeExchange(self.now), datetime(2026, 11, 1, 0, 5, tzinfo=timezone.utc))
        self.assertEqual(ev3["type"], "UNIVERSE_REFRESHED")
        self.assertEqual(len(j.read("universe_history.jsonl")), 2)
        shutil.rmtree(d, ignore_errors=True)

    def test_held_coin_stays_in_data_but_not_eligible(self):
        c = U.cycle_config(self.cfg, {"large": ["BTC-USD"], "mid": []}, {"OLD-USD"})
        self.assertIn("OLD-USD", c["universe"])
        self.assertNotIn("OLD-USD", c["eligible"])

    def test_lock_refuses_fixed_universe(self):
        from crypto_ai import lock as L
        tmp = tempfile.mkdtemp()
        pkg = os.path.join(tmp, "pkg")
        for sub in ("prompts", "strategies", "risk"):
            os.makedirs(os.path.join(pkg, sub))
        for f in ["PREREGISTRATION.md", "experiment.json", os.path.join("prompts", "trader_system_v1.md")] + L.LOCKED_CODE:
            shutil.copy(os.path.join(L.PKG_DIR, f), os.path.join(pkg, f))
        import json
        p = os.path.join(pkg, "experiment.json")
        cfg = json.load(open(p)); cfg["universe_rule"]["mode"] = "fixed"; json.dump(cfg, open(p, "w"))
        with self.assertRaises(RuntimeError):
            create_lock(os.path.join(tmp, "state"), pkg)
        shutil.rmtree(tmp, ignore_errors=True)


class TestLineup(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.j = Journal(self.dir)
        self.t0 = datetime(2026, 10, 5, 0, 5, tzinfo=timezone.utc)      # a Monday: rotation picks

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_views_large_vs_large_mid(self):
        sig = {a: {"trend": {"on": True}, "breakout": {"on": a == "UNI-USD"}, "dip": {"on": False},
                   "rotation": {"pick": False, "rank": 5}} for a in CFG["eligible"]}
        self.assertEqual(ai_view("ai_large", CFG, sig, Portfolio("ai_large", 1e4)), CFG["large"])
        v = ai_view("ai_largemid", CFG, sig, Portfolio("ai_largemid", 1e4))
        self.assertEqual(v[:10], CFG["large"])
        self.assertEqual(v[10], "UNI-USD")                         # strongest mid signal first
        self.assertLessEqual(len(v), 10 + CFG["arms"]["ai_largemid"]["max_mid_candidates"])

    def test_full_cycle_runs_every_arm_and_logs_signals(self):
        r = run_cycle(self.dir, CFG, FakeClient(self.t0), MockLLM(), now=self.t0, dry_run=True, require_lock=False)
        self.assertEqual(r["status"], "OK", r)
        self.assertEqual({e["arm"] for e in self.j.read("equity.jsonl")}, set(CFG["arms"]))
        sig = self.j.read("signals.jsonl")[0]["signals"]
        self.assertEqual(set(sig), set(CFG["eligible"]))
        rows = {r["arm"]: r for r in self.j.read("decisions.jsonl") if "view" in r}
        self.assertEqual(set(rows), {"ai_large", "ai_largemid"})
        self.assertEqual(rows["ai_large"]["scored_assets"], CFG["large"])
        prompt = self.j.read("prompts.jsonl")[0]["user_prompt"]
        self.assertIn("toolbox_signals", prompt)
        strat = [o for o in self.j.read("orders.jsonl") if o["arm"].startswith("s_")]
        self.assertTrue(strat, "at least one strategy arm should trade on the synthetic market")
        self.assertTrue(all(o["cause"] == "strategy" for o in strat))
