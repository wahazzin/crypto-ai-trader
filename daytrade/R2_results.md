# R2 — Short-term price rules after costs: results

Rules: `research/DAYTRADE_PREREG.md` (committed before data). 25 coins, hourly, fills at next hour's open, one open trade per coin per rule. Main costs ≈ 0.9–1.1% round trip.

## DESIGN 2022-01 → 2024-06

| Rule | Trades | Win rate | Avg win | Avg loss | **Expectancy/trade (after costs)** | t | Edge vs random entry | t | Expectancy at 10 bps fees | t |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | 3503 | 37% | +4.77% | -4.16% | **-0.88%** | -7.31 | +0.05% | -2.91 | -0.28% | -4.45 |
| D2 | 5786 | 30% | +3.15% | -2.90% | **-1.07%** | -14.02 | -0.06% | -5.32 | -0.47% | -8.83 |
| D3 | 2675 | 39% | +2.95% | -3.39% | **-0.89%** | -4.46 | +0.12% | +3.31 | -0.29% | +0.16 |
| D4 | 1649 | 33% | +3.22% | -2.85% | **-0.85%** | -8.13 | +0.18% | -0.41 | -0.25% | -3.62 |

## HOLDOUT 2024-07 → 2026-09

| Rule | Trades | Win rate | Avg win | Avg loss | **Expectancy/trade (after costs)** | t | Edge vs random entry | t | Expectancy at 10 bps fees | t |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | 5040 | 38% | +5.23% | -4.30% | **-0.67%** | -6.87 | +0.23% | -2.62 | -0.07% | -3.93 |
| D2 | 7339 | 34% | +3.71% | -2.99% | **-0.73%** | -11.95 | +0.25% | -4.81 | -0.13% | -7.50 |
| D3 | 3332 | 40% | +3.04% | -3.34% | **-0.78%** | -3.74 | +0.25% | +2.83 | -0.18% | +0.15 |
| D4 | 2338 | 36% | +3.22% | -2.85% | **-0.67%** | -9.24 | +0.36% | -0.60 | -0.07% | -4.17 |

Rules: **D1** = Momentum-24h (24h ret > +5%, hold 24h); **D2** = Prior-day breakout (close > yesterday's high, exit 00:00 UTC); **D3** = Flush reversal (1h ret ≤ −3%, hold 6h); **D4** = Volume-spike continuation (vol ≥ 4× median & +2%, hold 6h)

## Verdict (pre-registered: after-cost expectancy > 0 with t ≥ 2 AND edge vs random entry > 0 with t ≥ 2, ≥ 100 trades, in BOTH splits)

- D1 Momentum-24h (24h ret > +5%, hold 24h): design fail, holdout fail → **NO EVIDENCE**
- D2 Prior-day breakout (close > yesterday's high, exit 00:00 UTC): design fail, holdout fail → **NO EVIDENCE**
- D3 Flush reversal (1h ret ≤ −3%, hold 6h): design fail, holdout fail → **NO EVIDENCE**
- D4 Volume-spike continuation (vol ≥ 4× median & +2%, hold 6h): design fail, holdout fail → **NO EVIDENCE**

**Overall: NO EVIDENCE → no day-trading arm from these rules.**
