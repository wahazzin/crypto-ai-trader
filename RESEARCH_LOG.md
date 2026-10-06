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
