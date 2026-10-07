# Pre-registration — Do simple short-term price rules work on crypto after costs? (Research R2, phase 17)

**Written 2026-10-07, before any hourly data was fetched.** Git timestamp = proof. Changes only at
the bottom, dated, with a reason.

## 1. Question and prior

The project is "swing → day trading". Before any day-trading module exists, test whether the most
common short-term rules have an edge on our coins **after realistic costs**, each rule alone
(project rule 9), price/volume only (rule 8: sentiment is too slow at this speed, and R1 found none).

**Prior: low, mostly because of costs.** At Coinbase retail fees (0.40% per side) a round trip costs
~0.9% with spread and slippage. A rule holding for hours has to make that back every trade. The
equities program also rejected every short-term price rule it tested (Tests 1–4, 16–19).

## 2. Data

| Item | Value |
|---|---|
| Prices | Coinbase hourly candles (closed only), same source as the live bot |
| Coins | Today's eligible universe (large + mid) from the live rule |
| Period | 2022-01-01 → 2026-09-30 (same window as R1) |

## 3. The rules (textbook parameters, fixed now, never tuned)

All long-only. Signal on a closed hour → **enter at the next hour's open** → exit as stated.
**One open trade per coin per rule** (no overlapping trades = no fake independence).

| Rule | Entry | Exit |
|---|---|---|
| **D1 Momentum-24h** | 24h return > +5% | after 24 hours |
| **D2 Prior-day breakout** | hourly close > previous UTC day's high | at 00:00 UTC (end of that day) |
| **D3 Flush reversal** | 1h return ≤ −3% | after 6 hours |
| **D4 Volume-spike continuation** | 1h volume ≥ 4× median hourly volume of the prior 24h AND 1h return ≥ +2% | after 6 hours |

D4 is the same pattern the live scanner uses to wake the AI. If it has no edge alone, that's
useful to know about the wake-ups too.

## 4. Costs

- **Main:** 40 bps fee per side + 5 bps half-spread + slippage (2 bps BTC/ETH, 6 large alts,
  10 mid) per side ≈ 0.9–1.1% round trip. This is the live bot's cost model.
- **Sensitivity (reported, NOT a pass criterion):** 10 bps fee per side (what a low-fee / maker
  venue might cost). If a rule only works there, that's a venue question, not an edge we have.

## 5. Splits

- **DESIGN:** 2022-01-01 → 2024-06-30
- **SEALED HOLDOUT:** 2024-07-01 → 2026-09-30, looked at once after the design numbers are written.

## 6. Measures

Per rule, per split:
- trades, win rate, avg win, avg loss, **expectancy per trade after costs** (rule 6)
- **edge vs random entry:** each trade's gross return minus the same coin's average gross return
  over ALL windows of the same length in that split. This removes the bull/bear drift that would
  otherwise flatter or punish any long-only rule.
- t-stats from daily-aggregated trade results with Newey-West (5 days)

## 7. Verdict rules (fixed)

A rule **PASSES** only if ALL hold, in BOTH design and holdout:
1. expectancy per trade after main costs > 0, with t ≥ 2.0, and
2. edge vs random entry > 0, with t ≥ 2.0, and
3. at least 100 trades in each split.

Anything else = **NO EVIDENCE**. A pass means: candidate for a live paper day-trading arm, which
would get its own pre-registration and start date. It does not mean "trade it".

## 8. Ways we could fool ourselves

| Risk | Control |
|---|---|
| Survivorship (only today's coins) | Edge vs random entry in the same coin removes drift; stated in results |
| Using the signal candle's close as the fill | Fill at the NEXT hour's open |
| Overlapping trades counted as independent | One open trade per coin per rule; daily aggregation + Newey-West |
| Four rules, one lucky | All four reported; passing needs design AND holdout |
| Tuning thresholds | All thresholds above, written before data |
| Low-fee sensitivity used as a pass | Explicitly not a pass criterion |

## Clarification (2026-10-07, after the first run, before any interpretation; verdict unaffected)

The first output showed per-TRADE means next to t-stats computed on per-DAY means; for some rows
these disagreed in sign (trades cluster on volatile days). Results now show both, and a pass needs
BOTH the per-trade and the per-day mean > 0 plus t ≥ 2. This is stricter than the original wording,
not looser. No rule passed under either version.
