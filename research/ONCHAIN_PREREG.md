# Pre-registration — Does on-chain data predict crypto returns? (Research R3, phase 16)

**Written 2026-10-07, after a read-only feasibility probe (which metrics exist and from when; no
values were analysed) and before any metric was compared with prices.** Git timestamp = proof.

## 1. Question and prior

Last untested information source before deciding what else, if anything, the AI should see.
Popular claims: coins moving onto exchanges signal selling (bearish), coins leaving signal holding
(bullish); network growth (active addresses) leads price; "overvalued" coins (high MVRV) underperform.

**Prior: low-to-moderate.** These ideas are widely published and watched, so any edge should be
small or gone. Our news (R1) and day-trading (R2) tests both came back NO EVIDENCE.

## 2. Data (from the probe, `onchain/probe.md` on `crypto-ai-research`)

| Metric (Coin Metrics Community, free, CC BY-NC) | Coins |
|---|---|
| Exchange inflow / outflow (native units), supply held on exchanges | **BTC, ETH only** |
| Active addresses (AdrActCnt), MVRV (CapMVRVCur) | BTC, ETH, XRP, ZEC, QNT, LINK, ADA, UNI, XLM, LTC, AAVE, BCH (12) |

Prices: Coinbase daily closes (00:00 UTC), same as the live bot.

**Timing:** a metric for day *d* is only published after *d* ends, so it is used from day *d*+1:
the return window always starts at close(*d*+1). One full day of safety lag.

**Splits:** DESIGN 2016-06-01 → 2021-12-31 · SEALED HOLDOUT 2022-01-01 → 2026-09-30.

## 3. Tests (all fixed now)

**F1 — Exchange net flow, BTC and ETH (time series).** Net inflow = (inflow − outflow) / supply on
exchanges. Signal = its z-score vs the previous 30 days. Next 1-day and 7-day return.
Statistic: Spearman IC over days; t-stat with Newey-West (lag = horizon + 5). Each coin separately,
and pooled (both coins' ICs averaged per day).

**F2 — Exchange supply trend, BTC and ETH.** 30-day % change in supply held on exchanges → next
30-day return. Same statistic (lag 35).

**F3 — Network growth, cross-section of the 12 coins.** 30-day growth of active addresses (7-day
average vs the 7-day average 30 days earlier). Daily cross-sectional Spearman IC vs next 7-day
return in excess of those coins' equal-weight average. Mean daily IC, NW t (lag 12).

**F4 — Valuation, cross-section of the 12 coins.** MVRV rank vs next 30-day excess return (expected
sign: negative, i.e. high MVRV → worse). Mean daily IC, NW t (lag 35).

## 4. Verdict rules (fixed)

A test **PASSES** only if ALL hold:
1. |t| ≥ 2.0 in DESIGN, and the same sign with |t| ≥ 2.0 in the HOLDOUT, and
2. **economic check in the HOLDOUT:** a simple rule built only from the signal beats doing nothing
   different, after a 0.9% round trip per switch:
   - F1/F2: hold the coin, but sit in cash for the next horizon whenever the signal is in its worst
     decile (decile cut from DESIGN only), vs holding the coin all the time.
   - F3/F4: each day hold the top-3 coins by the signal's favourable direction (re-picked weekly),
     vs the equal-weight average of the 12 coins.

Anything else = **NO EVIDENCE**. A pass means: candidate for a new AI portfolio that also sees that
metric, started by a logged amendment and forward-tested like everything else.

## 5. Ways we could fool ourselves

| Risk | Control |
|---|---|
| **Backfilled exchange labels** (addresses identified as exchange-owned years later make old flows "know" the future) | Cannot be fully removed with free data. Stated up front: F1/F2 results are an UPPER bound on what was knowable in real time. A pass would still need forward testing |
| Publication lag | Metric of day *d* only used from *d*+1 |
| Two coins only (F1/F2) = low power, one regime can dominate | Both coins and pooled reported; design and holdout must agree |
| Overlapping windows (7d, 30d) inflate t | Newey-West with lag > horizon |
| Survivorship (coins alive today) | Excess returns vs the same coins; stated |
| Many tests, one lucky | 4 tests, all reported; pass needs design AND holdout AND economics |
