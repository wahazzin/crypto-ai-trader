# Pre-registration — Does crypto news predict crypto returns? (Research R1, roadmap phase 16)

**Written 2026-10-07, before any news data was fetched or scored.** The git timestamp of this file
is the proof. Nothing below changes after data is seen; changes go at the bottom with a date and
a reason.

## 1. Question and prior

Before giving the AI headlines (a new AI portfolio, phase 16), check whether news sentiment has
ANY predictive value for our coins. If it doesn't, feeding it to the AI adds tokens and noise.

**Prior: low.** The equities program's FinBERT tests found a clean null for average sentiment
(Test 13, 40,209 articles, |t| < 1.2 everywhere) and an *attention* effect (unusual news volume)
that was not about sentiment direction (Test 14). Crypto news is noisier and more promotional.
Expected result: NO EVIDENCE.

## 2. Data

| Item | Value |
|---|---|
| Source | Alpaca News API (Benzinga), crypto symbols, headlines + timestamps + symbols |
| Coins | Today's eligible universe from the live rule (large + mid), Alpaca symbol form (BTCUSD …) |
| Period | First month with real coverage (probe: ~2021–22, none in 2020) → 2026-09-30 |
| Prices | Coinbase daily candles (close = 00:00 UTC), same as the live bot |
| Scorer | FinBERT `ProsusAI/finbert` on headlines: score = P(positive) − P(negative), −1..+1. Same model as equities Tests 13–14. FinBERT can be backtested because it can't know what happened next |

Timing (no look-ahead): a headline published during UTC day *d* counts for day *d*. Its return is
close(*d*) → close(*d*+*h*). The headline is always before the return window starts.

## 3. Splits

- **DESIGN:** coverage start → 2024-06-30
- **SEALED HOLDOUT:** 2024-07-01 → 2026-09-30. Looked at once, after the design results are written down.

## 4. Tests (all fixed now)

**T1 — Average sentiment (Test 13 analog).** Per coin-day with ≥ 1 headline: mean score vs the
coin's next 1-day and 3-day return in excess of the equal-weight universe that day. Statistic:
pooled Spearman IC, t-stat with Newey-West (5 days). Also per-coin ICs, t-test across coins.

**T2 — Cross-sectional (the bot's own question).** Each day, across coins that had news: rank
correlation of sentiment vs next 1-day excess return. Mean daily IC, Newey-West t (5 days).

**T3 — Attention shocks (Test 14 analog).** Shock day = coin's headline count ≥ 3× its own median
on news days. Next 1/3/7-day excess return on shock days, all shocks and split into sentiment
terciles. Declustered: shocks of the same coin ≥ 10 days apart (the equities lesson: clustered
events fake significance).

## 5. Verdict rules (fixed)

A test **PASSES** only if ALL of these hold:
1. |t| ≥ 2.0 in DESIGN, and
2. same sign and |t| ≥ 2.0 in the HOLDOUT, and
3. the effect size beats a ~1% round trip (40 bps fee each way + spread/slippage) at that horizon, and
4. for T3: the result survives declustering.

Anything else: **NO EVIDENCE** for that test. No partial credit, no "almost".

## 6. What happens with the result

- **Any test passes** → design a new AI portfolio `ai_news` (headlines in its message), started by
  a logged amendment, compared with `ai_large` only over the overlap. Still forward-tested.
- **Nothing passes** → no news arm. Logged as a negative result, like equities Tests 13–14.

## 7. Ways we could fool ourselves (and the control)

| Risk | Control |
|---|---|
| Survivorship: only coins alive today | Excess returns vs the same coins' equal-weight index; stated in the result |
| Coverage grows over time (more news later) | Per-period counts reported; ICs per period |
| News written AFTER the move ("BTC jumps 8%…") | Same-day returns are never used; only the next day onward |
| Many tests, one lucky | 3 tests × 2–3 horizons are reported together; passing needs design AND holdout |
| Tuning thresholds after looking | Every threshold is in this file, before data |
| Headline tagged with many coins | Counted for each tagged coin; share of multi-coin headlines reported |
