# Crypto AI Trader — an AI that trades, and a test that won't let it lie

An autonomous AI trading bot for crypto: it reads the market, forms theses, decides what to buy,
hold and sell, and remembers why. It trades **paper money only**, inside hard risk rules written
in code that it cannot override, and it is graded by a statistical test fixed before it started.

**This repository does not contain a proven profitable strategy.** It contains the bot and the
apparatus that will find out whether it has any skill. "No evidence" is a legitimate result.

**Start here:** [`ROADMAP.md`](ROADMAP.md) — status, measured constraints, what happens next.

| File | What's in it |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | Where we are, hard constraints, next build, open decisions |
| [`RESEARCH_LOG.md`](RESEARCH_LOG.md) | Dated record of what was done and measured |
| [`crypto_ai/PREREGISTRATION.md`](crypto_ai/PREREGISTRATION.md) | The test: hypotheses, verdict rules, ways we could fool ourselves |
| [`crypto_ai/SPEC_v0.1.md`](crypto_ai/SPEC_v0.1.md) | Architecture, risk rules R1–R14, data flow |

---

## How one cycle works

```
Coinbase prices ──► features ──► AI (gpt-oss-120b, free)
                                    │  "buy ADA 12.5%, wrong if it closes below $0.26"
                                    ▼
                              RISK ENGINE (code)  ── can clip or reject anything
                                    ▼
                              PAPER EXCHANGE  ── fees 0.4%, real spread, slippage
                                    ▼
                         journal + portfolio + theses saved
                                    ▼
                    next cycle, the AI sees what happened
```

Next to the AI, four baselines trade the same market: **BTC hold, ETH hold, equal-weight basket,
simple trend rule**. If the AI can't beat these, it isn't good.

## What the AI can and can't do

| The AI decides | Code decides (AI can't touch) |
|---|---|
| Which coins, when, how much (as a % target) | Max per coin (35% BTC/ETH, 15% alts) |
| Its thesis and the price that proves it wrong | Max invested (80%), max alts together (40%) |
| Hold, add, reduce, exit, or do nothing | Stop-losses, daily-loss and drawdown circuit breakers |
| A confidence number (logged, never trusted) | Liquidity, spread and turnover limits |

## Universe

BTC, ETH, SOL, XRP, ADA, LINK, AVAX, LTC (USD pairs). DOGE and DOT were excluded: memecoin
dynamics and thin volume respectively.

## Run it

1. **Tests:** `python -m unittest discover -s tests -v`
2. **Local dry run (fake AI, no key needed):**
   `python -m crypto_ai.runner --state-dir crypto_ai_state_dryrun --dry-run`
3. **On GitHub:** Actions → *crypto_ai paper trader* → Run workflow → pick an action:
   - `smoke` — real AI, throwaway state (saved to the `crypto-ai-smoke` branch)
   - `lock` — freeze the rules and start the clock (**once**)
   - `run` — one real cycle (refuses until locked)
   - `report` — print performance (interim = informational only)

The experiment's real state lives on the `crypto-ai-data` branch, written only by GitHub Actions.

## Secrets (GitHub → Settings → Secrets and variables → Actions)

| Secret | Needed? |
|---|---|
| `GROQ_API_KEY` | Yes (free) |
| `OPENROUTER_API_KEY` | Optional backup, same model |
| `DISCORD_WEBHOOK_URL` | Optional circuit-breaker alerts |

Keys never go in code, chat, or commits. `.env` is git-ignored.

## Related projects

- Long-term investing research (equities):
  [`wahazzin/quant-trading-ten-strategies-rejected`](https://github.com/wahazzin/quant-trading-ten-strategies-rejected)
- Next after this one: a memecoin day trader/scalper (not started).
