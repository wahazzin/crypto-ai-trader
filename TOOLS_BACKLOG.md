# TOOLS BACKLOG — outside projects we plan to use, and WHEN

Nothing here gets installed "just in case". Each one is added when its phase starts, tested alone
first (project rule 9), and logged in `RESEARCH_LOG.md` when it goes in.
When a phase in `ROADMAP.md` starts, check this file first.

| # | Project | What it is | Add it when… | Phase | Status |
|---|---|---|---|---|---|
| 1 | [alpaca-py](https://github.com/alpacahq/alpaca-py) | Alpaca's official Python SDK | We build the Alpaca paper **mirror** (order-flow rehearsal; our simulator stays the scorer) | 7 | ⬜ after lock |
| 2 | [freqtrade](https://github.com/freqtrade/freqtrade) | Mature open-source crypto bot: backtesting, dry-run, hyperopt, FreqAI | We test **price-only day-trading rules** (no AI, so backtests are allowed) | 10 | ⬜ |
| 3 | [ccxt](https://github.com/ccxt/ccxt) | One library for 100+ exchanges' market data and orders | We need data beyond Coinbase: more venues, DEX-listed coins, project 3 | 10 / P3 | ⬜ |
| 4 | [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Multi-agent LLM framework (analyst, researcher, trader, risk roles) | We add **specialist agents** (news, sentiment). Ideas only; its backtest results are not evidence, since LLMs have seen that history | 9+ | ⬜ |
| 5 | Alpha Arena / nof1 (Oct 2025) | Real-money LLM trading contest | Reference, not a tool. One week + leverage = luck dominated. Re-read before trusting any short result | — | 📌 lesson |
| 6 | [DexScreener API](https://docs.dexscreener.com/) | Free DEX pair data: price, liquidity, volume, new pairs | Project 3 (memecoin trader) universe + data | P3 | ⬜ |
| 7 | [RugCheck](https://rugcheck.xyz/) | Solana token safety checks (mint/freeze authority, holder concentration, LP lock) | Project 3: hard filter before any memecoin is even considered | P3 | ⬜ |
| 8 | [vectorbt](https://github.com/polakowo/vectorbt) | Very fast vectorised backtesting in pandas | Alternative to freqtrade for mass-testing simple price rules | 10 | ⬜ optional |

## Security rules (non-negotiable)

1. Many GitHub "Solana / memecoin trading bot" repos are **malware that steals wallet keys**
   ([Cointelegraph report](https://cointelegraph.com/news/solana-trading-bot-github-malware-scam)).
   Only use the official repos linked above. Check the owner, stars and history before cloning.
2. Never put a real wallet private key or exchange key into any outside code. Paper only.
3. Read what a dependency does before adding it; pin its version in `requirements.txt`.
