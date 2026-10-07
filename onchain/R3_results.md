# R3 — On-chain data vs returns: results

Rules: `research/ONCHAIN_PREREG.md` (committed before analysis). Metric of day d used from d+1. **F1/F2 use exchange labels that are backfilled: treat any F1/F2 effect as an upper bound.**

| Test | Split | IC (pooled) | t | n | Per coin (IC, t) |
|---|---|---|---|---|---|
| F1_1d | DESIGN | +0.010 | +0.61 | 2040 | BTC +0.001 (+0.05), ETH +0.018 (+0.78) |
| F1_1d | HOLDOUT | +0.018 | +1.07 | 1734 | BTC +0.035 (+1.57), ETH +0.001 (+0.03) |
| F1_7d | DESIGN | -0.008 | -0.38 | 2040 | BTC -0.014 (-0.55), ETH -0.001 (-0.04) |
| F1_7d | HOLDOUT | -0.007 | -0.33 | 1733 | BTC -0.013 (-0.48), ETH -0.001 (-0.04) |
| F2_30d | DESIGN | -0.150 | -2.29 | 2040 | BTC -0.174 (-2.06), ETH -0.125 (-1.44) |
| F2_30d | HOLDOUT | +0.013 | +0.16 | 1710 | BTC +0.054 (+0.55), ETH -0.028 (-0.27) |
| F3_growth_7d | DESIGN | -0.003 | -0.12 | 1041 | — |
| F3_growth_7d | HOLDOUT | +0.030 | +1.90 | 1733 | — |
| F4_mvrv_30d | DESIGN | +0.065 | +1.43 | 1041 | — |
| F4_mvrv_30d | HOLDOUT | +0.009 | +0.27 | 1710 | — |

## Economic check (holdout only; direction and cut-offs from design)

- F1_1d BTC: rule -66.3% vs buy & hold +77.8% (153 exits)
- F1_1d ETH: rule -78.4% vs buy & hold -28.2% (179 exits)
- F1_7d BTC: rule +8.7% vs buy & hold +77.8% (79 exits)
- F1_7d ETH: rule -24.7% vs buy & hold -28.2% (102 exits)
- F2_30d BTC: rule +77.8% vs buy & hold +77.8% (0 exits)
- F2_30d ETH: rule -28.2% vs buy & hold -28.2% (0 exits)
- F3_growth_7d top-3 vs equal-weight: rule -79.2% vs equal-weight +74.8%
- F4_mvrv_30d top-3 vs equal-weight: rule -46.9% vs equal-weight +74.8%

## Verdict (|t| ≥ 2 design AND same-sign |t| ≥ 2 holdout AND economic check)

- F1_1d: statistics fail, economics fail → **NO EVIDENCE**
- F1_7d: statistics fail, economics fail → **NO EVIDENCE**
- F2_30d: statistics fail, economics fail → **NO EVIDENCE**
- F3_growth_7d: statistics fail, economics fail → **NO EVIDENCE**
- F4_mvrv_30d: statistics fail, economics fail → **NO EVIDENCE**

**Overall: NO EVIDENCE → no on-chain arm.**
