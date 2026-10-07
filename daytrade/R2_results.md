# R2 — Short-term price rules after costs: results

Rules: `research/DAYTRADE_PREREG.md` (committed before data). 25 coins, hourly, fills at next hour's open, one open trade per coin per rule. Main costs ≈ 0.9–1.1% round trip.

Each mean is shown two ways: **per trade** (every trade counts once) and **per day** (each day's trades averaged first, then days averaged). The t-stat tests the per-day version (Newey-West, 5 days). When the two disagree in sign, trades cluster on a few days and the per-trade number is misleading.

## DESIGN 2022-01 → 2024-06

| Rule | Trades | Win rate | Avg win | Avg loss | **Expectancy/trade after costs** (per trade / per day) | t | Edge vs random entry (per trade / per day) | t | At 10 bps fees (per trade / per day) | t |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | 3503 | 37% | +4.77% | -4.16% | **-0.88% / -1.53%** | -7.31 | +0.05% / -0.62% | -2.91 | -0.28% / -0.93% | -4.45 |
| D2 | 5786 | 30% | +3.15% | -2.90% | **-1.07% / -1.62%** | -14.02 | -0.06% / -0.62% | -5.32 | -0.47% / -1.02% | -8.83 |
| D3 | 2675 | 39% | +2.95% | -3.39% | **-0.89% / -0.58%** | -4.46 | +0.12% / +0.43% | +3.31 | -0.29% / +0.02% | +0.16 |
| D4 | 1649 | 33% | +3.22% | -2.85% | **-0.85% / -1.08%** | -8.13 | +0.18% / -0.05% | -0.41 | -0.25% / -0.48% | -3.62 |

## HOLDOUT 2024-07 → 2026-09

| Rule | Trades | Win rate | Avg win | Avg loss | **Expectancy/trade after costs** (per trade / per day) | t | Edge vs random entry (per trade / per day) | t | At 10 bps fees (per trade / per day) | t |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | 5040 | 38% | +5.23% | -4.30% | **-0.67% / -1.40%** | -6.87 | +0.23% / -0.53% | -2.62 | -0.07% / -0.80% | -3.93 |
| D2 | 7339 | 34% | +3.71% | -2.99% | **-0.73% / -1.61%** | -11.95 | +0.25% / -0.65% | -4.81 | -0.13% / -1.01% | -7.50 |
| D3 | 3332 | 40% | +3.04% | -3.34% | **-0.78% / -0.58%** | -3.74 | +0.25% / +0.44% | +2.83 | -0.18% / +0.02% | +0.15 |
| D4 | 2338 | 36% | +3.22% | -2.85% | **-0.67% / -1.09%** | -9.24 | +0.36% / -0.07% | -0.60 | -0.07% / -0.49% | -4.17 |

Rules: **D1** = Momentum-24h (24h ret > +5%, hold 24h); **D2** = Prior-day breakout (close > yesterday's high, exit 00:00 UTC); **D3** = Flush reversal (1h ret ≤ −3%, hold 6h); **D4** = Volume-spike continuation (vol ≥ 4× median & +2%, hold 6h)

## Verdict (pre-registered: after-cost expectancy > 0 with t ≥ 2 AND edge vs random entry > 0 with t ≥ 2, ≥ 100 trades, in BOTH splits)

- D1 Momentum-24h (24h ret > +5%, hold 24h): design fail, holdout fail → **NO EVIDENCE**
- D2 Prior-day breakout (close > yesterday's high, exit 00:00 UTC): design fail, holdout fail → **NO EVIDENCE**
- D3 Flush reversal (1h ret ≤ −3%, hold 6h): design fail, holdout fail → **NO EVIDENCE**
- D4 Volume-spike continuation (vol ≥ 4× median & +2%, hold 6h): design fail, holdout fail → **NO EVIDENCE**

**Overall: NO EVIDENCE → no day-trading arm from these rules.**
