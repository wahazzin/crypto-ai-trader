"""Shared test config: the real experiment.json, but with the universe FIXED to the offline lists
(tests have no network). Mirrors exactly what runner builds each cycle via cycle_config."""
import copy

from crypto_ai.lock import load_config
from crypto_ai.universe import cycle_config


def test_cfg():
    cfg = copy.deepcopy(load_config())
    r = cfg["universe_rule"]
    r["mode"] = "fixed"
    return cycle_config(cfg, {"large": r["fixed_large"], "mid": r["fixed_mid"]}, set())
