# CRYPTO AI TRADER — ROADMAP
*Started October 2026. Read this file first when picking the project back up.*

This file exists so that if the project stalls, gets confusing, or is picked up after a break, the
next person (or the next AI session) can read one file and know exactly where things stand.

---

## 1. THE GOAL, STATED HONESTLY

Build an **AI trading bot**: an AI that looks at the crypto market, forms its own theses, decides
what to buy, hold and sell, and lives with its own past decisions, all inside hard risk rules it
cannot override.

The deliverable is **evidence** of whether that AI is any good, not profits. It trades paper money
only, next to simple baselines, and it is scored by a test written down *before* it started.

**Current honest status: nothing is proven. The bot has only made smoke-test decisions. No edge
exists until the pre-registered test says so.**

### Where this fits (the three projects)

| # | Project | Style | Repo | Status |
|---|---|---|---|---|
| 1 | Equities research engine | Long-term investing | `wahazzin/quant-trading-ten-strategies-rejected` | Paper forward tests running |
| **2** | **Crypto AI trader (this repo)** | **Swing → day trading** | `wahazzin/crypto-ai-trader` | **Built, smoke-tested, not locked** |
| 3 | Memecoin day trader / scalper | Fast, price-driven | not created yet | Starts after project 2 |

---

## 2. WHERE WE ARE

| Phase | Status |
|---|---|
| 0 — Pre-registration + spec (`crypto_ai/PREREGISTRATION.md`, `SPEC_v0.1.md`) | ✅ Drafted, ⚑ items open |
| 1 — Core: data, features, portfolio, paper exchange, risk engine (R1–R14) | ✅ Built |
| 2 — AI decision layer (free gpt-oss-120b via Groq, OpenRouter backup) | ✅ Built, smoke test passed |
| 3 — Baselines in parallel (BTC hold, ETH hold, equal-weight, trend rule) | ✅ Built |
| 4 — Numeric invalidation levels (`exit_below`, `review_above`) | ✅ Built 2026-10-06 |
| 5 — Fast scanner (every 5 min, code only) + AI woken on events | ✅ Built 2026-10-06, 82 tests, smoke-tested with the real AI |
| 5b — Rule-based universe (large 10 + mid), strategy toolbox, two AI portfolios | ✅ Built 2026-10-07, 99 tests, smoke-tested with the real AI |
| 5c — Toolbox backtest, each strategy alone, sealed holdout | ✅ Done 2026-10-07 (RESEARCH_LOG). Dip lost money in both periods → D7 |
| 6 — **Lock the experiment, turn on the schedule** | ⬜ **Next. Blocked on D3 (run length) and D7 (dip)** |
| 7 — Alpaca paper mirror (order-flow rehearsal, not the scorer) | ⬜ After lock |
| 8 — Random-policy arms (is the AI better than luck?) | ⬜ Planned v0.2 |
| 9 — New inputs, one at a time (news → sentiment → on-chain) | ⬜ Each tested alone first |
| 10 — Day-trading module (price/technical only) | ⬜ Planned |
| 11 — Decision point (verdict) | ⬜ Date set at lock |

---

## 3. HARD CONSTRAINTS WE HAVE MEASURED (not assumed)

**C1 — Fees.** Coinbase-level retail fee: **0.4% per side** (confirmed 2026-10-06). A round trip
costs **≥0.8%** plus spread and slippage. A trade has to move more than that just to break even.
*Implication: trading often bleeds money. Scanning often is free; trading often is not.*

**C2 — The free AI has a daily budget.** Groq free tier for gpt-oss-120b: 30 requests/min,
1,000 requests/day, 8,000 tokens/min, **200,000 tokens/day**. One decision uses about
**5,600 tokens** (measured, smoke test 2026-10-06: 2,953 in + 2,676 out).
→ **At most ~35 AI decisions per day.** An AI call every 5 minutes (288/day) is impossible on the
free tier. Fixed 6-hour cycles use 4/day.

**C3 — The AI is slow.** One decision took **6 seconds**. Fine for swing trading, useless for
scalping, where the edge is gone in milliseconds and belongs to firms with co-located servers.

**C4 — GitHub's scheduler.** Minimum interval 5 minutes, and runs are often delayed several
minutes at busy times. Public repo = unlimited free minutes.

**C6 — The free AI can only read so much at once.** Groq free tier caps one minute at 8,000
tokens. 8 coins already use ~5,300 per call, so the AI can only look at **roughly 12–15 coins**
per decision. Wider scanning has to be done by code (the strategy toolbox), not the AI.

**C5 — Alpaca paper fills are optimistic.** Alpaca's own docs: paper trading ignores market
impact and slippage, and fills orders larger than the real available liquidity. So Alpaca can
mirror our trades but **cannot be the scorekeeper**; our stricter simulator is.

---

## 4. THE SCANNER (built 2026-10-06): fast code checks + event-woken AI

The idea: watch the market every few minutes **for free with plain code**, and only wake the AI
when something is worth thinking about.

```
every 5 min (code, no AI, free)                    every 6 h (AI, scored)
 ├─ check hard stops ─────────► sell if hit          ├─ full decision + outlook for all 8 coins
 ├─ price crossed an exit_below? ┐                    └─ this is what the IC test grades
 ├─ price reached review_above?  ├─► wake the AI
 ├─ move > X% in 1h?             │   (capped, ~20/day,
 └─ volume spike?               ┘    leaving headroom under C2)
```

Why this shape:
- The scored test stays clean: the regular 6-hour outlooks are what the statistics grade.
  Event calls are extra decisions, logged and analysed separately.
- It respects C1 (looking ≠ trading) and C2 (the AI budget).
- It turns `exit_below` from words into something the bot actually acts on within minutes.

Code: `crypto_ai/scanner.py`. Settings: `experiment.json → scanner`. One GitHub schedule every
5 minutes runs it; it runs the 6h cycle itself when one is due, so two jobs never write at once.

| Setting | Value |
|---|---|
| Big move trigger | ≥ 4% in the last hour |
| Volume spike trigger | ≥ 4× the median hourly volume of the last 24h, with ≥ 1.5% move |
| Level triggers | Held coin crosses its `exit_below` or `review_above` (fires once per level) |
| Cooldown (move/volume) | 3 hours per coin |
| AI budget | ≤ 20 wake-ups/day, ≥ 30 min apart, none in the 30 min before a cycle |
| Quiet scans | Write nothing (no commit). Heartbeat once an hour |

Known asymmetry (recorded in PREREGISTRATION): the AI gets extra decision chances between
cycles; the strategy arms don't. All constrained arms get the same 5-minute stop checks.

---

## 5. HOW WE USE OUTSIDE GITHUB PROJECTS (full list: [`TOOLS_BACKLOG.md`](TOOLS_BACKLOG.md))

We don't install anything "just in case". Each tool comes in only when a phase needs it, and gets
tested alone first (project rule 9).

| Project | What it is | When we use it |
|---|---|---|
| `ccxt` | One Python library for 100+ exchanges | When we need data beyond Coinbase (project 3) |
| `freqtrade` | Mature open-source crypto bot with backtesting and dry-run | Phase 10: testing price-only day-trading rules |
| `alpaca-py` | Alpaca's official SDK | Phase 7: Alpaca paper mirror |
| `TradingAgents` (TauricResearch) | Multi-agent LLM trading framework | Ideas for agent roles in phase 9+. Its backtest results are NOT evidence (LLMs have seen the history) |
| Alpha Arena (nof1) | Real-money LLM trading contest, Oct 2025 | A warning, not a tool: one week, leverage, luck dominated |
| DexScreener / RugCheck APIs | Memecoin market and safety data | Project 3 |

**Security rule:** many GitHub "Solana/memecoin trading bot" repos are malware that steals wallet
keys. Never run one with a real key, never install one without reading it, paper only.

---

## 6. DECISIONS WAITING FOR THE OWNER

| # | Question | Status |
|---|---|---|
| D1 | Fee assumption 0.4%/side | ✅ Confirmed 2026-10-06 |
| D2 | Build the fast scanner (§4)? | ✅ Built 2026-10-06 |
| D3 | Run length / first decision point | ⏳ Deferred by owner. **Must be set before the lock**, then only extendable |
| D4 | Alpaca: create a new, separate crypto paper account | ⏳ Owner action, after lock |
| D5 | Strategy toolbox: code computes 3–5 known strategies, shows signals to the AI, each strategy also trades alone | ✅ Owner approved 2026-10-07. Start list: trend, breakout+volume, dip-in-uptrend, relative-strength rotation. More strategies later via research |
| D6 | Universe: chosen by a written rule (`crypto_ai/universe.py`), not by hand or by past returns | ✅ Owner chose BOTH tiers 2026-10-07 → two AI portfolios: `ai_large`, `ai_largemid` |
| D7 | The dip strategy lost money in both backtest periods. Keep it, drop it, or replace it? | ⏳ Waiting |
| D8 | Add an SPY comparison (project rule 5) before any go-live discussion | ⏳ Planned, needs a non-Coinbase data source |

---

## 7. RULES THAT DON'T BEND

1. Paper money only. No path to real orders exists in this code (a test enforces it).
2. The risk engine is code, not AI. The AI cannot change limits, sizes or stops beyond tightening.
3. AI confidence is logged and checked against outcomes, never trusted.
4. No AI backtests: the model may have memorised the past. Forward testing only.
5. After the lock, rules change only through `AMENDMENTS.md`, with a written reason.
6. Interim results are informational only. No verdict before the decision point.
7. Keys live in GitHub Secrets. Never in code, never in chat, never in a commit.
