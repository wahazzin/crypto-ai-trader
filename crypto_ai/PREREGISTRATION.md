# Pre-Registration — Crypto AI Paper Trader (`crypto_ai` v0.2)

**Status: DRAFT — NOT LOCKED.** This document becomes binding when
`python -m crypto_ai.lock --create` writes the lock file (SHA-256 of this file,
`experiment.json`, the trader prompt, and the code that defines the rules: `strategies/toolbox.py`,
`risk/engine.py`, `universe.py`). After lock, the runner refuses to run if any
of them change. Items marked ⚑ are proposals awaiting the owner's confirmation.
Nothing below may be changed after seeing results; changes go through §9.

Written before any simulated trade exists. Paper money only. This codebase contains no
broker or exchange-order code at all — it is paper-only by construction.

---

## 1. Question and prior

Does an LLM given **price, volume, its own portfolio state and the signals of four fixed code
strategies** produce (a) forecasts with real predictive value, and (b) a paper portfolio that
beats those same strategies trading alone, and simple holding, after costs?
Sub-question: does letting it also look at smaller (mid-tier) coins help or hurt?

**Prior: low.** The equities program went 0-for-19 on price-based signals in liquid markets.
Crypto is noisier and costlier. The expected outcome is NO EVIDENCE. That is recorded here
so a null result can't be reframed later as "the AI just needs more data."

## 2. Hypotheses

- **H0-P / H1-P (primary, predictive):** mean cross-sectional Spearman IC between the AI's
  per-asset outlook score and the asset's next-24h return is 0 / greater than 0.
- **H0-E / H1-E (secondary, economic):** the AI arm's risk-adjusted performance is no better
  than constraint-matched baselines and random policies / is better.

## 3. Design (exact values live in `experiment.json`)

| Item | Value |
|---|---|
| Universe rule (`universe.py`) | Coinbase USD pairs, online; excluding stablecoins, wrapped/staked copies and memecoins (lists in `experiment.json`); ≥300 daily candles of history; ranked by 30-day USD volume. **LARGE** = top 10. **MID** = ranks 11–30 with ≥ $5M average daily volume. Uses no past returns. Re-screened on the first cycle of each UTC month; every screen logged in `universe_history.jsonl`. A coin that drops out can still be sold but not bought (R15). |
| Why this rule | Liquidity makes paper fills believable and manipulation harder. Choosing by past returns would be survivorship + look-ahead bias (CryptoRank 2026: ~72% of coins ever in the top 100 are effectively dead). The MID tier exists because size is a documented crypto factor (Liu, Tsyvinski & Wu, J. Finance 2022) and is where a small account can go that funds skip. |
| Data | Coinbase Exchange public REST. Closed candles only (never the in-progress candle). |
| Cadence | Scored decision cycles at 00:00, 06:00, 12:00, 18:00 UTC. Plus a 5-minute code scanner (stops, breakers, triggers) that may wake the AI between cycles: ≤20/day, ≥30 min apart (`experiment.json → scanner`, ROADMAP §4). Wake-up decisions are logged to `event_*.jsonl`, are NOT part of the IC test, and their trades DO count in AI P&L. Budget per AI arm: ≤10/day |
| Capital | $10,000 simulated per arm, all arms start at the same first-cycle snapshot |
| Instrument | Spot, long-only, no leverage, no shorting, USD cash only, market orders only |
| Costs (confirmed by owner 2026-10-06) | 40 bps fee/side + measured half-spread + slippage (2 bps BTC/ETH, 6 bps large alts, 10 bps mid + size impact). Sensitivity re-runs at 10 and 60 bps |
| Fills | Priced from a quote fetched AFTER the LLM response returns — never at the price the AI saw |
| Model | `gpt-oss-120b`, open weights, via free API tiers (Groq primary, OpenRouter backup serving the SAME weights). Never falls back to a different model. Provider + returned model id logged on every call |
| Randomness | temperature 0; prompt and full response logged |

**Arms (all run every cycle on the identical snapshot):**

| Arm | Type | Rule |
|---|---|---|
| `ai_large` | Subject | LLM decides on the LARGE tier (10 coins) + anything it holds. Sees toolbox signals. Through the risk engine |
| `ai_largemid` | Subject | Same, plus up to 5 MID coins per cycle that the toolbox flags (ranking in `toolbox.mid_candidates`, fixed). Mid coins capped at 10% each |
| `s_trend` | Strategy alone | close > SMA50 and SMA50 rising (vs 10 days ago). All eligible coins. Same risk engine, stops, costs |
| `s_breakout` | Strategy alone | Enter: close > prior 20-day high on ≥1.5× 20-day avg volume. Exit: close < prior 10-day low |
| `s_dip` | Strategy alone | Enter: ≥8% drop over 3 days while SMA50 rising and close within 10% of SMA50. Exit: close > SMA10 or 10 days |
| `s_rotation` | Strategy alone | Top 3 eligible coins by 28-day return (only if > 0), re-picked weekly (Monday 00:00 UTC) |
| `btc_hold` | Reference benchmark | Buy BTC at start, hold. Not risk-constrained |
| `eth_hold` | Reference benchmark | Same for ETH |
| `ew_basket` | Reference benchmark | Equal-weight the LARGE tier, rebalanced first cycle of each UTC month |
| random policies | Constraint-matched challenger (analysis-time) | 1,000 random policies through the same risk engine and costs, calibrated ONLY on each AI arm's realised gross exposure and turnover, never on returns. Built before the first interim report |

Strategy parameters are textbook defaults fixed before any test and never tuned. Strategy arms
size equal weight across active coins aiming at 80% gross; the risk engine clips them like the AI.
Each strategy was also backtested alone (`research/backtest_toolbox.py`, design 2020–2023 vs sealed
holdout 2024–) before going live; that backtest informs, it does not gate, and its known
survivorship bias is stated in the output.

The constraint-matched arms separate "the AI decides well" from "the risk engine helps."

**Known structural asymmetry (found by unit test, recorded before any trade):** the risk engine
caps turnover at 25% of equity per 24h and gross exposure at 80%. The AI and strategy arms
therefore need ~4 days to build a full position and never exceed 80% invested, while
`btc_hold`/`eth_hold`/`ew_basket` are 100% invested from cycle one. In a rising market the
reference benchmarks get a structural head start unrelated to decision quality; in a falling one
they get a structural penalty. This is exactly why the primary test is IC (unaffected by
constraints) and why the economic comparison that matters is AI vs the strategy arms and the
random policies, which face identical constraints.

## 4. Explicitly NOT tested in v0.1

News, social sentiment, on-chain data, a "full information" arm, an AI arm WITHOUT toolbox
signals (ablation), memecoins (project 3), leverage, shorting, limit orders, partial fills. When news/sentiment modules exist, each new
information menu becomes a NEW arm with its own start date (via §9) and is compared to other
arms only over the overlapping window. Existing AI arms are never retro-fitted.

## 5. Outcome measures

**Primary — predictive value.** Every cycle the AI must output an integer outlook in
{-2..+2} for EVERY coin it can see (expected direction of its next-24h return; 0 only when it
genuinely has no view). **Only the LARGE tier is scored** (a fixed 10-coin cross-section; mid
candidates change every cycle). Each AI arm is tested separately; both must be reported. Outlooks are logged and never used by the risk engine or execution.
Forward return = snapshot mid at t+24h / mid at t − 1 (exact alignment: 4 cycles later).
Daily IC = mean over that UTC day's cycles of the cross-sectional Spearman IC. Statistic =
mean daily IC with a Newey-West t-stat (lag 5 days). Also computed at 72h (12 cycles).

**Secondary — economic.** Return, annualised return, vol, Sharpe, Sortino (daily, √365),
max drawdown, turnover, fees, slippage, alpha/beta vs `btc_hold` (OLS on daily returns).
Reported for all arms, always beside the constraint-matched arms.

**Diagnostics (never decision criteria):** confidence-vs-outcome calibration (Rule 11),
thesis invalidation usefulness, stop-outs, risk-engine rejection reasons, token cost.

---

## 6. Power analysis — why the primary test is IC, and why 12 months is the minimum

**Run length (owner confirmed 2026-10-07): 12 months minimum** from the lock, then the first decision
point. It may be extended (once, to 24 months, per §7), never shortened, so results can't decide when we stop.

Computed before writing any threshold (80% power, 5% two-sided):

| Test | Detectable at 6 mo | 12 mo | 24 mo | 60 mo |
|---|---|---|---|---|
| Sharpe gap vs BTC (portfolio corr 0.9) | 1.77 | **1.25** | 0.89 | 0.56 |
| Alpha vs BTC, t>2 (residual vol 20%) | 57%/yr | **40%/yr** | 28%/yr | 18%/yr |
| **Cross-sectional IC, N=8 assets (N=10 now: slightly more power)** | 0.078 | **0.055** | 0.039 | — |

Consequences, fixed now:
1. Portfolio P&L cannot confirm a realistic edge inside 12-24 months. It is secondary.
2. IC is the only measure with usable power on this timescale. It is primary.
3. The modal outcome at 12 months is **INCONCLUSIVE or NO EVIDENCE**. That is not failure and
   is not a reason to loosen any threshold.
4. Any P&L result before the decision point, good or bad, is noise.

## 7. Verdict rules (fixed)

**Decision points:** 12 months after lock and, if extended once, 24 months. Requires
≥1,240 completed cycles (85% of 1,460 scheduled per year), otherwise the point is postponed.
No verdict before the first decision point; interim reports print the banner in §10.

**Primary (IC at 24h):**

| Verdict | Condition |
|---|---|
| PREDICTIVE | IC24 ≥ +0.03 AND t ≥ 2.0 AND IC72 > 0 AND IC24 > 0 in both halves of the window |
| INCONCLUSIVE → extend once | IC24 ≥ +0.02 AND 1.0 ≤ t < 2.0 (collapses to NO EVIDENCE at 24 months) |
| HARMFUL (anti-predictive) | IC24 ≤ −0.03 AND t ≤ −2.0. Does NOT imply "trade the opposite" — that needs its own pre-registration |
| NO EVIDENCE | anything else |

**Secondary (economic) — assessed ONLY if primary = PREDICTIVE.** TRADABLE requires ALL:
(i) Sharpe(AI) > Sharpe of EVERY strategy arm (`s_*`); (ii) Sharpe(AI) > Sharpe(`btc_hold`);
(iii) AI Sharpe ≥ 95th percentile of the matched random policies; (iv) net alpha vs BTC > 0
after costs; (v) maxDD(AI) ≤ maxDD(`btc_hold`). Alpha t-stat is reported, not required
(unreachable at feasible T, §6). If the verdict flips between 10 and 60 bps fees it is
labelled **cost-fragile**.

Final labels: `NOT EVALUABLE` · `NO EVIDENCE` · `HARMFUL` · `PREDICTIVE, NOT PROVEN TRADABLE`
· `PREDICTIVE AND TRADABLE (provisional, needs an independent replication arm)`.

## 8. Ways we could fool ourselves, and the control for each

| Risk | Control |
|---|---|
| LLM has seen historical prices in training → backtest is contaminated | **No historical backtest of the AI arm. Forward-only.** Baselines may be backtested. |
| Model silently updated mid-experiment | Open-weights model (fixed weights file); provider and API-returned model id logged every call |
| Free tier shrinks or disappears mid-experiment | Same weights served by a second provider. Each missed cycle counts against the 85%-coverage rule; if coverage becomes impossible, the arm is closed via amendment, never swapped to a different model |
| Different providers behave slightly differently (quantisation, serving stack) | Provider logged per call; IC reported split by provider as a diagnostic |
| Prompt tweaked after a bad week | Prompt file hashed into the lock |
| Perfect fills at the price the AI saw | Fills use a post-response quote, plus fee, spread, slippage |
| Look-ahead via in-progress candle | Closed candles only; test enforces it |
| Many metrics, report the best | One primary test, fixed above |
| Luck mistaken for skill | Constraint-matched baselines + random-policy distribution |
| Universe chosen with hindsight | Structural rule, frozen at lock; delisting rule below |
| Survivorship | Delisted asset: position force-sold at last valid bid −5%, asset removed for ALL arms, logged |
| Quiet human intervention | Every intervention is an amendment; git history is public and timestamped |
| Confidence treated as probability | Logged only; never read by risk engine or execution |
| Good month → "it works" | Banner in §10; no changes based on interim results |

**Multiple comparisons (added 2026-10-07, before lock).** Two AI arms are tested. A PREDICTIVE
verdict for either requires its own criteria to be met; we report both and do not pick the better
one after the fact. Strategy-arm comparisons are descriptive.

**Scanner asymmetry (added 2026-10-06, before lock).** The AI arms can act between cycles when
woken; strategy arms act only at cycles. Both arms get identical 5-minute stop checks. The primary
test (IC of scheduled outlooks) is unaffected. For the secondary P&L comparison we additionally
report the AI's P&L from scheduled-cycle trades only vs including wake-up trades, so we can see
whether wake-ups helped or hurt.

## 9. Amendments

Bug fixes to code are allowed and go through normal git history. Changes to anything hashed
in the lock (this file, `experiment.json`, the prompt) require an entry appended to
`AMENDMENTS.md` (date, what, why, hashes) and either a NEW arm or a documented statement that
the change cannot affect results. Amendments never rewrite history, never delete an arm.

## 10. Interim reporting rule

Every report before a decision point prints, verbatim:

> **INTERIM — INFORMATIONAL ONLY. Interim performance is not evidence of edge.**

The owner commits not to call the system successful, and not to change any parameter, based on
a good week or month.
