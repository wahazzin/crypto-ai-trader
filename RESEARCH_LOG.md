# RESEARCH LOG — Crypto AI Trader

Dated, append-only. What was done, what was measured, what it means. Newest at the bottom.

---

## 2026-09-29 — Design and v0.1 build (in the equities repo)

- Wrote `PREREGISTRATION.md` and `SPEC_v0.1.md` before any code ran.
- Power analysis: over 12 months, a portfolio-P&L comparison can only detect a Sharpe gap of
  ~1.25 vs BTC. Realistic edges are far smaller, so **P&L is secondary** and the primary test is
  the cross-sectional IC of the AI's outlook scores (detectable IC ≈ 0.055 at 12 months).
- Built v0.1: Coinbase public data, closed candles only, paper exchange with fees + spread +
  slippage, deterministic risk engine (R1–R14), 4 baselines, append-only journal, spec lock.
- Owner refused paid LLM APIs → free open-weights **gpt-oss-120b** (Groq primary, OpenRouter
  backup, same weights; never falls back to a different model).

## 2026-10-06 — Moved to its own repo

- Moved from `wahazzin/quant-trading-ten-strategies-rejected` to `wahazzin/crypto-ai-trader`.
  Reason: separate secrets. The crypto bot never sees the equities Alpaca keys.
- Replaced the dependency on the old repo's Discord helper with `crypto_ai/notify.py`.
  A test now forbids importing the old `bot` package.
- 66 tests passed in the new repo.

## 2026-10-06 — First real run refused (correct)

- The first `run` returned `LOCK_MISMATCH: no lock.json`. That's the design working: real cycles
  can't run before the rules are frozen.
- Added `--smoke` mode: real AI, no lock, throwaway state saved to the separate
  `crypto-ai-smoke` branch, so it can never mix with the experiment record.

## 2026-10-06 — Smoke test with the real AI: plumbing works

| Item | Result |
|---|---|
| Provider / model | Groq / `openai/gpt-oss-120b` |
| Valid JSON on first try | Yes |
| Latency | 6.0 s |
| Tokens | 2,953 in + 2,676 out ≈ 5,600 per decision |
| AI action | Bought ADA 12.5% and AVAX 12.5%. Risk engine approved both |
| Baselines | All 4 traded correctly; trend rule correctly clipped by the 25% daily turnover cap |

**Problem found:** the AI's invalidation conditions were vague ("significant price drop or
overbought signal"). Nothing can check that, so the thesis could never be proven wrong.

**Fix:** every BUY/ADD must now include `exit_below`, a concrete price below the current price.
It's validated by code (missing or above-price → response rejected). Each cycle the AI sees
`exit_below_breached` / `review_above_reached` for its open theses. 70 tests pass.

**Constraint measured:** at ~5,600 tokens per call and Groq's 200,000 tokens/day free limit,
the AI can be asked at most ~35 times per day. That rules out calling the AI every few minutes
and shaped the scanner proposal in ROADMAP.md §4.

## 2026-10-06 — Scanner built (owner: "it should scan every few minutes")

- Asking the AI every 5 minutes is impossible on the free tier (C2) and trading that often bleeds
  fees (C1). Built a hybrid instead: free code checks every 5 minutes, AI woken only on triggers.
- Single entry point (`crypto_ai.scanner`) so the 6h cycle and the scans can never write the
  state at the same time.
- Wake-ups are logged separately (`event_decisions.jsonl`) so the pre-registered IC test only ever
  sees the regular 6h outlooks.
- 12 new tests (82 total): due-cycle handling, quiet scans write nothing, lock required, level
  triggers fire once, daily cap, spacing, quiet window before cycles, stops on 5-min candles,
  move/volume detection.

**Smoke test on GitHub with the real AI (2026-10-06 11:07 UTC):**

| Step | Result |
|---|---|
| Scheduled cycle | OK, 3,257 in / 2,055 out tokens, 14 paper fills across the 5 arms |
| Forced trigger | Fake "AVAX crossed its exit level" → scanner woke the AI |
| AI wake-up answer | Valid first try, 4.5 s. Held AVAX, reset `exit_below` to $10.50 and set `review_above` $12.50 |
| Scanner state | Budget counted (1/20 today), trigger marked fired, heartbeat written |

Interpretation: plumbing only. Two decisions say nothing about skill.

## 2026-10-07 — Universe: from a hand-picked list to a rule

Owner challenged the original 8 coins (picked for liquidity). Agreed they need a better basis, but
**not past profitability**: choosing coins because they went up is survivorship + look-ahead bias.
CryptoRank (2026): of 1,539 coins that were ever top-100, 71.9% are effectively dead; the
probability a top-100 coin disappears within 5 years is 62%. A universe of today's survivors hides
all of them.

What legitimately justifies a universe:
1. **A written rule** using only non-return facts: on Coinbase vs USD, not a stablecoin / wrapped
   coin / memecoin, >= 300 days of history, liquid enough that paper fills are believable.
2. **Research on where edges live**: Liu, Tsyvinski & Wu (Journal of Finance 2022, data
   2014–2018) find crypto returns are explained by market, **size** and **momentum** factors.
   Smaller coins and momentum are where the documented premia are, which supports a MID tier
   and the trend/rotation strategies. Caveat: old sample, smaller coins cost more to trade.
3. **Testing strategies, not coins**: toolbox strategies are price-only, so they CAN be backtested
   across the whole eligible universe with a sealed holdout. That says whether a strategy works
   on a class of coins, without cherry-picking the coins.

**Screen run on GitHub, 2026-10-07 05:30 UTC:** 400 USD products online, 306 eligible.
Top 10 by 30-day volume: BTC, ETH, XRP, ZEC, SOL, NEAR, SUI, QNT, LINK, ADA. AVAX and LTC (in the
original 8) are now MID tier (ranks 12 and 17). PUMP and USELESS showed up at MID ranks and were
added to the memecoin exclusion list (project 3). Caveat: one 30-day window; ZEC's rank looks
like a recent volume burst.

New constraint (C6): Groq free tier = 8,000 tokens/minute, so the AI can read roughly 12–15 coins
per decision. A wider universe must be scanned by code.

## 2026-10-07 — v0.2 lineup built: rule-based universe, strategy toolbox, two AI portfolios

Owner approved: coins by rule (large 10 + mid tier), a "strategy toolbox" whose signals the AI
sees, each strategy also trading alone, and two AI portfolios (large only vs large + mid) so the
mid-cap question gets its own answer. 99 tests.

**Smoke test on GitHub (real data, real AI, throwaway state):**

| Item | Result |
|---|---|
| Universe rule | 25 eligible coins: large = BTC, ETH, XRP, ZEC, SOL, NEAR, SUI, QNT, LINK, ADA; 15 mid |
| Cycle | OK in 158 s (incl. 65 s spacing between the two AI calls) |
| ai_large | Valid first try (4.6k in / 2.6k out tokens). Bought ADA, NEAR, SUI, SOL at 10% each, each with a numeric exit level |
| ai_largemid | Valid first try (6.0k in / 2.0k out). Saw 5 mid candidates (ZRO, ENA, ONDO, AERO, UNI); bought QNT and NEAR |
| Strategy arms | All 4 traded; 9 portfolios total |
| Forced wake-up | ai_largemid answered (8.6 s). ai_large hit Groq **HTTP 413: 8,000 tokens/minute exceeded**. Cause: the smoke test fires the wake-up seconds after the cycle's last AI call, from a new process. Fix: a tokens-per-minute 413 now waits 62 s and retries (test added). On the real schedule, cycle and scans are >= 5 min apart. |

## 2026-10-07 — Toolbox backtest: each strategy alone (rule 9), design vs sealed holdout (rule 3)

`research/backtest_toolbox.py` on GitHub, 25 coins (today's eligible set), daily, the live
signal functions on the same 120-day window, live sizing caps, 18% stop, costs 40 bps fee +
5 bps half-spread + 2/6/10 bps slippage per side. Parameters fixed before the run, never tuned.

**Signal audit:** recomputed by hand from raw candles for BTC, UNI and AERO: signals match.
"Breakout on almost everywhere" in the live run is real (broad September rally on high volume).
Over all years, breakout is on 31% of coin-days, trend 34%, rotation 15%, dip 12%.

| Strategy | Design 2020–23 Sharpe | Holdout 2024– Sharpe | Holdout total | Holdout max DD | Holdout expectancy/trade | Beats EW hold (design / holdout) |
|---|---|---|---|---|---|---|
| btc_hold | 1.00 | 0.74 | +93% | −53% | — | — |
| ew_hold (same coins) | 0.93 | 0.57 | +57% | −61% | — | — |
| trend | 0.95 | 1.02 | +133% | −35% | +0.2% (win rate 18%) | no / YES |
| **breakout** | **1.42** | **1.16** | **+159%** | **−35%** | **+1.7%** (win rate 33%) | **YES / YES** |
| dip | −0.38 | −0.83 | −45% | −51% | −0.3% (win rate 62%) | no / no |
| rotation | 1.09 | 0.84 | +86% | −39% | +4.9% | no / YES |

**What this does and doesn't say:**
1. **dip lost money in both periods** despite winning 58–62% of trades: small wins, bigger losses.
   Textbook case of rule 6: win rate alone is meaningless.
2. **breakout is the only one that beat holding the same coins in both periods**, with lower drawdown
   than BTC. Promising, not proven: one history, one parameter set.
3. trend wins only 18–20% of trades but is roughly break-even per trade: few large wins.
4. **Survivorship bias inflates every absolute number.** Only coins alive today are included. The
   EW-hold comparison carries the same bias, which is why it's the yardstick.
5. Not yet compared with SPY (project rule 5). Coinbase has no SPY. To add before any go-live talk.
6. This backtest informs; it does not unlock anything. The live forward test decides.

## 2026-10-07 — Pre-lock additions: scorecard, order-book fills, horizon, roadmap

- **Dip kept** as a known loser; instead of hiding it, the AI now sees a **strategy scorecard** each
  cycle: the backtest summary plus every strategy's live paper record. That's the honest version
  of "learning from failure": evidence across many trades, not a reaction to one loss. A proper
  learning arm (trade reviews → weekly statistics → a separate `ai_learner` vs an identical arm
  without lessons) is roadmap phase 15.
- **Order-book fills:** buys/sells now walk Coinbase's live level-2 book for the actual order size
  (plus a 2/6/10 bps latency buffer). Prices were already live; this makes the fill itself real-ish.
- **Horizon** stated in the AI's instructions: short-to-mid term, days to weeks; longer holds allowed
  while the evidence holds (owner, 2026-10-07).
- **Run length 12 months** confirmed by owner.
- Considered and rejected: running the model locally (Ollama). gpt-oss-120b needs ~80 GB of memory
  and the PC would have to stay on 24/7; the 20b version fits ~16 GB but is a weaker, different
  model. Swapping models mid-test would also mix two "brains" in one result. Other models
  (e.g. Gemini free tier) can come later as their OWN arms.
- ROADMAP rewritten as a phase-by-phase plan (phases 11–18 + project 3). 102 tests.

## 2026-10-07 — Final smoke test, then LOCKED and LIVE

Last smoke (real AI, throwaway state): cycle OK (ai_large 4.5k in / 1.9k out tokens, ai_largemid
5.6k / 2.0k); both AIs woke on a forced exit-level breach and both sold the affected positions,
which is the behaviour the instructions ask for. Compact JSON cut the AI's input by ~24%, which fixed
the wake-up that had hit Groq's 8k tokens/minute cap.

**Lock created 2026-10-07T06:38:37Z** (code `ab4ee29`). Fingerprinted: PREREGISTRATION.md,
experiment.json, the trader prompt, strategies/toolbox.py, risk/engine.py, universe.py. The
pre-registration file still says "DRAFT" in its header: editing it now would break the lock, and the
lock file itself is the record of when it became binding. 5-minute schedule switched on.
First decision point: 2027-10-07 (needs >= 1,240 completed cycles).
