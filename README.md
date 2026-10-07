# Crypto AI Trader — an AI that trades, and a test that won't let it lie

An autonomous AI trading bot for crypto: it reads the market, forms theses, decides what to buy,
hold and sell, and remembers why. It trades **paper money only**, inside hard risk rules written
in code that it cannot override, and it is graded by a statistical test fixed before it started.

**This repository does not contain a proven profitable strategy.** It contains the bot and the
apparatus that will find out whether it has any skill. "No evidence" is a legitimate result.

**Status: LIVE on paper since 2026-10-07 06:38 UTC** (locked; 12-month test; first verdict 2027-10-07).

**Start here:** [`ROADMAP.md`](ROADMAP.md) — the phase-by-phase plan, measured constraints, decisions.

| File | What's in it |
|---|---|
| [`ROADMAP.md`](ROADMAP.md) | Where we are, hard constraints, next build, open decisions |
| [`RESEARCH_LOG.md`](RESEARCH_LOG.md) | Dated record of what was done and measured |
| [`TOOLS_BACKLOG.md`](TOOLS_BACKLOG.md) | Outside GitHub projects we'll use, and when |
| [`crypto_ai/PREREGISTRATION.md`](crypto_ai/PREREGISTRATION.md) | The test: hypotheses, verdict rules, ways we could fool ourselves |
| [`crypto_ai/SPEC_v0.1.md`](crypto_ai/SPEC_v0.1.md) | Architecture, risk rules R1–R14, data flow |

---

## How it runs

Every **5 minutes**, plain code (free) checks stops, circuit breakers and triggers. Every **6 hours**
the AI makes its full, scored decision. Between cycles the code wakes the AI only when something
happens: one of its exit prices is crossed, a 4%+ move in an hour, or a real volume spike.

### One AI decision

```
Coinbase prices ──► features ──► AI (gpt-oss-120b, free)
                                    │  "buy ADA 12.5%, wrong if it closes below $0.26"
                                    ▼
                              RISK ENGINE (code)  ── can clip or reject anything
                                    ▼
                              PAPER EXCHANGE  ── fees 0.4%, walks the live order book
                                    ▼
                         journal + portfolio + theses saved
                                    ▼
                    next cycle, the AI sees what happened
```

**Nine paper portfolios run side by side**, all with $10k:

| Portfolio | What it is |
|---|---|
| `ai_large` | The AI, looking at the 10 largest coins |
| `ai_largemid` | The AI, also shown up to 5 smaller coins the strategies flag |
| `s_trend`, `s_breakout`, `s_dip`, `s_rotation` | Four fixed code strategies, each trading alone (no AI) |
| `btc_hold`, `eth_hold`, `ew_basket` | Just holding: BTC, ETH, or the 10 large coins equally |

The AI sees the four strategies' signals as evidence. If it can't beat the best of them trading
alone, the AI adds nothing.

## What the AI can and can't do

| The AI decides | Code decides (AI can't touch) |
|---|---|
| Which coins, when, how much (as a % target) | Max per coin (35% BTC/ETH, 15% large alts, 10% mid) |
| Its thesis and the price that proves it wrong | Max invested (80%), max alts together (40%) |
| Hold, add, reduce, exit, or do nothing | Stop-losses, daily-loss and drawdown circuit breakers |
| A confidence number (logged, never trusted) | Liquidity, spread and turnover limits |

## Which coins

Picked by a written rule each month (`crypto_ai/universe.py`), never by hand or by past returns:
Coinbase USD pairs, no stablecoins / wrapped coins / memecoins, at least 300 days of history,
ranked by 30-day trading volume. **Large** = top 10. **Mid** = the next 20, if they trade at least
$5M a day. Run the screen any time with the `screen` action.

## Run it

1. **Tests:** `python -m unittest discover -s tests -v`
2. **Local dry run (fake AI, no key needed):**
   `python -m crypto_ai.runner --state-dir crypto_ai_state_dryrun --dry-run`
3. **On GitHub:** Actions → *crypto_ai paper trader* → Run workflow → pick an action:
   - `smoke` — real AI: one cycle + one forced wake-up, throwaway state (`crypto-ai-smoke` branch)
   - `lock` — freeze the rules and start the clock (**once**)
   - `run` — one scanner tick; runs the 6h cycle when due (refuses until locked)
   - `report` — print performance (interim = informational only)
   - `screen` — run the coin-selection rule now
   - `backtest` — test each toolbox strategy alone on past data (results on the `crypto-ai-research` branch)

The experiment's real state lives on the `crypto-ai-data` branch, written only by GitHub Actions.
**24/7:** `crypto_ai_loop.yml` scans every 5 minutes around the clock and restarts itself.
**Weekly check-in:** every Monday, `reports/weekly/<week>.md` on that branch (trades, win rate, avg
win vs avg loss, expectancy, drawdown, vs BTC and SPY). Preview any time with `weekly_preview`.
**Alpaca mirror:** `ai_large`'s trades are copied to the Alpaca *paper* account for the 13 coins it
lists; `mirror/fills.jsonl` compares Alpaca's fill price with ours. Our simulator stays the scorer.

## Secrets (GitHub → Settings → Secrets and variables → Actions)

| Secret | Needed? |
|---|---|
| `GROQ_API_KEY` | Yes (free) |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Separate crypto **paper** account: SPY benchmark + mirror |
| `OPENROUTER_API_KEY` | Optional backup, same model |
| `DISCORD_WEBHOOK_URL` | Optional circuit-breaker alerts |

Keys never go in code, chat, or commits. `.env` is git-ignored.

## Related projects

- Long-term investing research (equities):
  [`wahazzin/quant-trading-ten-strategies-rejected`](https://github.com/wahazzin/quant-trading-ten-strategies-rejected)
- Next after this one: a memecoin day trader/scalper (not started).
