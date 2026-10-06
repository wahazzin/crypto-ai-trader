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

**Current honest status: nothing is proven. The bot has made one test decision. No edge exists
until the pre-registered test says so.**

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
| 1 — Core: data, features, portfolio, paper exchange, risk engine (R1–R14) | ✅ Built, 70 tests |
| 2 — AI decision layer (free gpt-oss-120b via Groq, OpenRouter backup) | ✅ Built, smoke test passed |
| 3 — Baselines in parallel (BTC hold, ETH hold, equal-weight, trend rule) | ✅ Built |
| 4 — Numeric invalidation levels (`exit_below`, `review_above`) | ✅ Built 2026-10-06 |
| 5 — **Fast scanner (every 5 min, code only) + AI woken on events** | ⬜ **Proposed — waiting for owner OK (§4)** |
| 6 — Lock the experiment, turn on the schedule | ⬜ Blocked on §6 decisions |
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

**C5 — Alpaca paper fills are optimistic.** Alpaca's own docs: paper trading ignores market
impact and slippage, and fills orders larger than the real available liquidity. So Alpaca can
mirror our trades but **cannot be the scorekeeper**; our stricter simulator is.

---

## 4. PROPOSED NEXT BUILD: fast scanner + event-woken AI

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

**Open questions for the owner:** OK to build? Trigger thresholds start as proposals and get
fixed before the lock.

---

## 5. HOW WE USE OUTSIDE GITHUB PROJECTS

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
| D2 | Build the fast scanner (§4)? | ⏳ Waiting |
| D3 | Run length / first decision point | ⏳ Deferred by owner. **Must be set before the lock**, then only extendable |
| D4 | Alpaca: create a new, separate crypto paper account | ⏳ Owner action, after lock |

---

## 7. RULES THAT DON'T BEND

1. Paper money only. No path to real orders exists in this code (a test enforces it).
2. The risk engine is code, not AI. The AI cannot change limits, sizes or stops beyond tightening.
3. AI confidence is logged and checked against outcomes, never trusted.
4. No AI backtests: the model may have memorised the past. Forward testing only.
5. After the lock, rules change only through `AMENDMENTS.md`, with a written reason.
6. Interim results are informational only. No verdict before the decision point.
7. Keys live in GitHub Secrets. Never in code, never in chat, never in a commit.
