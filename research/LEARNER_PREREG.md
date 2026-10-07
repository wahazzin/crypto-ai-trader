# Pre-registration — Does the AI trade better when shown its own track record? (Phase 15, "learner")

**Written 2026-10-07, day 1 of the live run, before ANY AI trade has closed** (the only AI exit so
far is one QNT sale). Nothing below can have been shaped by learner results, because none exist.
Git timestamp = proof. Changes only at the bottom, dated, with a reason, before the arms start.

## 1. Question and prior

Owner: "how does teaching an AI failure not make it learn from that failure? Everyone has to fail
to succeed." Project rule 10: a loss doesn't teach the model anything by itself; learning has to be
designed and tested.

Our model's weights never change (free gpt-oss-120b, no fine-tuning). The only way it can "learn"
is **in-context**: we show it facts about its own past trades and it may act differently.
The question is whether that helps, measured against an identical AI that doesn't get the facts.

**Prior: low.** LLMs over-react to small samples and invent stories to fit them. A few dozen trades
is mostly noise, so the lessons can easily teach the wrong thing. That's why it's tested, not assumed.

## 2. Design

Two NEW arms, started on the same cycle with fresh $10,000 each, same rules as `ai_large`:

| Arm | Same as ai_large (model, prompt, coins = large tier, risk engine, costs) | Plus |
|---|---|---|
| `ai_learner` | yes | a **TRACK RECORD** block: statistics computed by code from closed AI trades |
| `ai_twin` | yes | the same block heading with "No track record shown in this portfolio." |

The twin exists because comparing the learner with `ai_large` would mix in a different start date
and different market conditions. Only the twin isolates the lessons.

**Lessons are numbers computed by code, not AI-written essays.** Self-written reviews from the same
model can't be checked, and they burn the free token budget. Code statistics are factual and
reproducible. (This replaces the roadmap's earlier "AI writes a review of each trade" idea, for the
reasons above, before anything was built.)

### The TRACK RECORD block (recomputed every Monday 00:00 UTC, fixed for the week)

Source: every closed trade of every AI arm (`ai_large`, `ai_largemid`, `ai_learner`, `ai_twin`;
same model, same prompt, so it's the same "player"), after all fees. Closed trades as computed by
`analytics/weekly.closed_trades`. Shown:

1. Overall: trades, win rate, avg win, avg loss, **expectancy per trade**.
2. Split by each of: entry type (scheduled cycle vs wake-up), stated confidence (<60, 60–74, ≥75),
   toolbox signals at entry (trend / breakout / dip / rotation on vs off), exit type (exit level hit
   vs AI sell vs risk engine), holding time (<1 day, 1–3 days, >3 days), tier (large vs mid).
3. Exits: average coin move in the 72 h AFTER each AI sell (did selling early help or hurt?).

**Noise guard:** a group is shown only with ≥ 8 trades. Every number is printed with its trade count
and the line "small samples are mostly noise; change behaviour only for large, consistent gaps."

## 3. Start rule

Both arms start on the first scheduled cycle on or after **2026-11-09** (month 2) on which the AI
arms have **≥ 30 closed trades combined**. If that hasn't happened by 2027-01-04, start anyway (the
block then shows whatever exists) and log it. Start = an amendment request through the normal
amendment process, so the lock records it.

## 4. Token budget (measured, not guessed)

Day 1 measured use: ~95,000 tokens/day for the 2 AI arms incl. wake-ups (~7,500 per call), against
Groq's free cap of 200,000/day. Two more arms on scheduled cycles add ~60,000/day. So:
- `ai_learner` and `ai_twin` decide on the 4 scheduled cycles per day.
- Wake-ups for them: **only their own exit-level breaches**, max 3 per arm per day (same for both).
- If the weekly report shows > 90% of the cap used, the backup provider (same model) answers
  overflow; both arms are always treated identically.

## 5. Tests (decision at the main decision point, 2027-10-07)

**Primary — performance:** daily return of `ai_learner` minus `ai_twin`, after fees. Mean > 0 with
Newey-West t ≥ 2.0 (lag 5).

**Required mechanism check:** the learner must actually behave differently in the direction the
block points. For each group the block flagged (≥ 8 trades, expectancy below the overall one by more
than half the overall avg loss), the learner's share of new trades in that group must be lower than
the twin's. If behaviour didn't change, any performance gap is luck, whatever its t-stat.

**Secondary (reported, not pass criteria):** IC of each arm's outlook (as in the main test),
confidence calibration of each arm (rule 11), max drawdown of each.

## 6. Verdict

- **LEARNING HELPS** = primary passes AND mechanism check passes.
- **LEARNING HURTS** = mean < 0 with t ≤ −2.0. Then the block is a liability: never added elsewhere.
- Anything else = **NO EVIDENCE**, which with ~11 months and two noisy arms is the most likely
  outcome, stated now so it isn't a surprise.

A pass means the block becomes a candidate for the main AI arms in a NEW pre-registered run. It does
not change any running arm.

## 7. Ways we could fool ourselves

| Risk | Control |
|---|---|
| Learner and twin differ by more than the block | Identical code path; twin gets the same heading; started together; same wake-up rules |
| One lucky streak | Daily differences, Newey-West, 11 months, plus the mechanism check |
| Lessons fitted to noise (the AI "learns" a fluke) | ≥ 8-trade groups, noise warning in the block; that risk is exactly what the test measures |
| Peeking and tuning the block mid-run | Block format fixed here; changes only via logged amendment, which resets the comparison clock |
| Sharing data the twin can't see | Twin sees the same market data, toolbox and scorecard; only the track record differs |
| Token cap hits one arm, not the other | Identical budgets; overflow to the same model on the backup provider for both |
