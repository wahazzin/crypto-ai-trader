# crypto-ai-trader

A **paper-trading-only** experiment: can a free open-weights LLM (gpt-oss-120b, via Groq) make crypto
portfolio decisions that beat simple baselines after realistic costs?

No real money. No exchange keys. The code cannot place real orders (a test enforces this).

## How it works (every 6 hours)
1. Pull closed candles + live quotes for 8 liquid coins from Coinbase's public API.
2. The AI sees market features, its own portfolio and its saved theses, then proposes trades.
3. A deterministic risk engine (rules R1–R14) approves, clips or rejects every proposal.
4. Approved trades fill on a simulated exchange with fees, spread and slippage.
5. Four baselines run in parallel: BTC hold, ETH hold, equal-weight basket, simple trend rule.

The AI's "confidence" is logged, never trusted. The verdict comes from a pre-registered statistical test
(`crypto_ai/PREREGISTRATION.md`), not from the equity curve.

## Run it
- **Tests:** `python -m unittest discover -s tests -v`
- **Local dry run (mock AI, no key):** `python -m crypto_ai.runner --state-dir crypto_ai_state_dryrun --dry-run`
- **Real cycle:** GitHub → Actions → *crypto_ai paper trader* → Run workflow → `run`

## Secrets (GitHub repo secrets, never in code)
- `GROQ_API_KEY` — required (free)
- `OPENROUTER_API_KEY` — optional backup, same model
- `DISCORD_WEBHOOK_URL` — optional breaker alerts

## Docs
- `crypto_ai/PREREGISTRATION.md` — hypotheses, verdict rules, what would fool us
- `crypto_ai/SPEC_v0.1.md` — architecture, risk rules, data flow

Split out of `wahazzin/quant-trading-ten-strategies-rejected` on 2026-10-06 so this bot never shares
secrets with the equities accounts.
