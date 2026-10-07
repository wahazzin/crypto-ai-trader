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

## 2026-10-07 — Alpaca account probe (read-only) + scheduler reliability

**Alpaca (new separate crypto paper account, keys in GitHub Secrets):**
- Account ACTIVE, **crypto_status ACTIVE** from Sweden. Paper cash $100k.
- Lists 36 USD crypto pairs, but only **13 of our 25 eligible coins** (6/10 large): BTC, ETH, XRP,
  SOL, LINK, ADA, UNI, AVAX, LTC, ONDO, BCH, AAVE, ARB. **Missing: ZEC, NEAR, SUI, QNT** (large) and
  8 mid coins. Both AIs' first buys (NEAR, QNT) are not on Alpaca.
  → Alpaca can only be a PARTIAL order-flow mirror. It can't be the venue for the whole universe.
- **SPY daily bars work** (IEX feed): benchmark for rule 5 is available.
- **Crypto news works**: 19 BTC/ETH/SOL articles in the last 24h; 411 in March 2023; **0 in March
  2020**, so the sentiment backtest window starts ~2021–2022, not 2015 as the docs suggest.

**Scheduler:** GitHub's cron is unreliable at our cadence. The equities repo's "hourly" job actually
fired every ~4–6 h (2026-10-06/07), and this repo's `*/5` schedule fired 0 times in its first hour.
The 6h cycles need >= 85% completion for the verdict (>= 1,240/yr), so an external trigger is needed.

**Fix deployed 07:48 UTC:** `crypto_ai_loop.yml`, a self-renewing loop (scan every 5 min for ~5h40m,
then dispatch the successor; hourly cron as backup restarter; one concurrency group so there's never
a second writer). First tick wrote a heartbeat at 07:48 UTC. cron-job.org (external trigger) was
the alternative; its verification email never arrived, and the loop needs no third party or token.

## 2026-10-07 — Weekly check-in report + Alpaca mirror

- **Weekly report** (`crypto_ai/analytics/weekly.py`, project rule 2): per portfolio, this week and
  since start: return, vs SPY, vs BTC, drawdown now / max, fills, closed round trips, win rate, avg
  win $ vs avg loss $, expectancy $ per trade (all fees included), fees; plus cycle-completion health.
  Written by the live loop every Monday into `reports/weekly/`. A preview at ~1.5 h after go-live
  showed every portfolio down by exactly its fees so far (−0.18% to −0.46%), as expected.
- **Paper-only guard refined:** it forbade the word "alpaca" anywhere in the package, which also
  blocked read-only SPY prices. It now forbids order code and trading endpoints specifically.
- **Alpaca mirror** (`mirror/alpaca_mirror.py`, outside the experiment package): copies `ai_large`'s
  fills to the Alpaca PAPER account (hard-coded paper endpoint), skips coins Alpaca doesn't list,
  logs Alpaca-vs-simulated fill price per order. Started after order row 37 (no history replay).
- On 1-minute scanning: rejected for this project. Stops already use each candle's true low, and
  decisions are 6-hourly with multi-day holds, so 1-minute checks add API load and nothing else.
  Sub-minute speed belongs to project 3 (memecoins, live price stream).

## 2026-10-07 — Phase 14: honesty checks built (in every weekly check-in)

`crypto_ai/analytics/diagnostics.py`, per AI arm:
1. **Better than luck?** The AI's scheduled decisions are replayed through a simple engine (cycle
   snapshots, same risk rules, modelled fills), next to 100 random policies (1,000 at the decision
   point) through the same engine. The random policies copy only the AI's *behaviour* (how often it
   trades, how many coins, what sizes), never returns. Reported: the AI's percentile among them.
2. **Wake-ups worth it?** Closed trades split by what opened them (scheduled vs wake-up), plus live
   equity vs the scheduled-only replay.
3. **Confidence vs outcome (rule 11):** buys bucketed by stated confidence with next-24h/72h returns
   and hit rate; plus the outlook "staircase" (avg next-24h return per outlook score −2..+2).
Tests use synthetic markets: an AI that buys the only rising coin beats > 80% of random policies;
calibration and wake-up attribution are checked on hand-built cases. 112 tests.
First data point: both AIs' first buys were 80–85% confidence (ai_large) and 70–79% (ai_largemid).

## 2026-10-07 — Amendment A1: thin mid coins no longer block a scan or cycle

At 08:33 UTC one scan was skipped as a DATA_FAULT because VVV-USD (mid tier) had no trade for more
than 180 s, so its ticker looked stale. The same rule applied to the 6h cycle: one quiet mid coin
could cost a scored cycle (the verdict needs >= 85% of cycles). Fix: a stale/invalid quote on a
mid coin that no portfolio holds now just leaves that coin out (event COINS_LEFT_OUT). Large-tier
coins, BTC and any held coin still block, as before. Recorded as amendment **A1** through the new
request mechanism (`crypto_ai/amendment_requests.json` → applied and logged by the live loop into
lock.json + AMENDMENTS.md). Made on day 0, before any result existed. 114 tests.

## 2026-10-07 — Research R1: crypto news vs returns — **NO EVIDENCE** (clean null)

Rules pre-registered in `research/NEWS_PREREG.md` (commit 6ee0a97, before any data). Full output:
`news/R1_results.md` on the `crypto-ai-research` branch.

**Data:** 29,764 Alpaca/Benzinga headlines tagged with our 25 coins, 2021-03 → 2026-09 (real coverage
starts 2022; 12 headlines in 2021). Very uneven: BTC 21,432, ETH 13,670, SOL 3,518, XRP 2,723, most
others 15–800. 35% of headlines tag more than one coin. 27,833 unique headlines scored by FinBERT;
sanity check passed (most negative: "Bitdeer reports net loss…"; most positive: "Solana's technical
fundamentals remain strong…"). Design 2022 → 2024-06 (4,464 coin-days), holdout 2024-07 → 2026-09
(4,015 coin-days).

| Test | Design t | Holdout t | Verdict |
|---|---|---|---|
| T1 avg sentiment → next 1d excess return | +0.40 | −0.53 | NO EVIDENCE |
| T1 → next 3d | −0.47 | +0.94 | NO EVIDENCE |
| T2 cross-sectional IC, next 1d | −1.06 | −0.37 | NO EVIDENCE |
| T2 cross-sectional IC, next 3d | −1.61 | +0.04 | NO EVIDENCE |
| T3 attention shocks (declustered), next 1d | −1.33 | +1.33 | NO EVIDENCE (sign flips) |
| T3 → next 3d | +0.48 | −0.73 | NO EVIDENCE |
| T3 → next 7d | −0.31 | −0.39 | NO EVIDENCE |

**Reading it:**
1. Same result as the equities program (Tests 13–14): headline sentiment doesn't predict returns,
   in design or holdout, at 1 or 3 days, pooled or cross-sectionally.
2. Two tempting-looking things that are NOT findings: the holdout's raw 1-day shock effect (t +2.00)
   dies when declustered (t +1.33) and has the opposite sign in design; and the positive-sentiment
   tercile at 7 days is positive in both periods (+1.3%, +1.8%) but on 25 and 16 events, and terciles
   were descriptive, not a pre-registered test. Chasing either would be data-mining.
3. Limits: FinBERT is a proxy for "can text predict anything"; an LLM reads better. But with zero
   signal from sentiment AND from attention, the prior that headlines add value is now very low.

**Decision (per the pre-registration):** no `ai_news` arm. Phase 16's news step is closed. Next
information candidates stay in the roadmap (sentiment from social data, on-chain), each with its
own pre-registration.

## 2026-10-07 — Research R2: short-term (day-trading) price rules — **NO EVIDENCE** after costs

Rules pre-registered in `research/DAYTRADE_PREREG.md` (before data). 25 coins, Coinbase hourly
candles 2022-01 → 2026-09, fill at the next hour's open, one open trade per coin per rule, live cost
model (~0.9–1.1% round trip). Full output: `daytrade/R2_results.md` on `crypto-ai-research`.

| Rule | After-cost expectancy per trade, design / holdout | Edge vs random entry (per day, t), design / holdout | Verdict |
|---|---|---|---|
| D1 24h momentum (+5%, hold 24h) | −0.88% / −0.67% | −0.62% (−2.91) / −0.53% (−2.62) | NO EVIDENCE |
| D2 Prior-day breakout (to 00:00) | −1.07% / −0.73% | −0.62% (−5.32) / −0.65% (−4.81) | NO EVIDENCE |
| D3 1h flush ≤ −3%, hold 6h | −0.89% / −0.78% | **+0.43% (+3.31) / +0.44% (+2.83)** | NO EVIDENCE (cost-killed) |
| D4 Volume spike + 2%, hold 6h | −0.85% / −0.67% | −0.05% (−0.41) / −0.07% (−0.60) | NO EVIDENCE |

**What it says:**
1. **Every rule loses money after Coinbase-retail costs, in both periods, by a lot** (t from −3.7 to −14).
   At these fees, day trading on simple price rules is structurally a losing game.
2. **One real effect: short-term reversal (D3).** Buying a coin right after a ≥3% one-hour drop beats a
   random entry by ~+0.4% per trade, in design AND the sealed holdout (t +3.3, +2.8). It is real, but
   about half the round-trip cost; even at 10 bps fees it's only break-even (+0.02%). Same story as the
   equities program's short-term reversal (Test 3): real, but eaten by costs.
3. **Chasing short-term strength is worse than random** (D1, D2: negative edge, t −2.6 to −5.3): buying
   after a pop tends to buy local tops. D4 (the same pattern the live scanner uses to wake the AI) has
   no edge either way. That's fine for a wake-up (it's attention, not an order), and it's a useful prior
   for judging the AI's wake-up trades in the phase 14 checks.
4. Win rates of 30–40% with avg win > avg loss still lose: rule 6 again, expectancy is what matters.

**Decision (per pre-registration):** no day-trading arm from these rules. A day-trading module only
becomes worth testing with near-zero trading costs (maker orders / low-fee venue): that's a venue
question for the go-live discussion, logged in the roadmap, not something to fake in a backtest.
