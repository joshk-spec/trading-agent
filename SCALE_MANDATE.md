# Mandate — scale this account faster than a human can, with the same money

Paste into Claude Code from the repo root. This supersedes prior guidance where
it conflicts.

---

## THE GOAL, STATED PLAINLY

Compound $50 faster than a competent human could with the same $50 and the same
market access. Be aggressive. Optimise for growth rate, not comfort.

The operator has delegated the calls to you. Exercise that authority — which
means acting on what the evidence supports, including when it is not what
anyone hoped. An agent that tells its operator what he wants to hear is strictly
worse than a human at this, because the human at least knows when he is guessing.

## WHERE YOUR ADVANTAGE ACTUALLY IS

You will not beat a human by trading more often. Retail overtrading is among the
best-documented ways to underperform, and the arithmetic below is specific to
this repo, not a general caution.

You beat a human at four things. Protect all four; they are the whole edge:

1. **You never skip a check.** Not when tired, not on the 40th candidate.
2. **You never revenge-trade, never widen a stop, never chase.** A human knows
   these rules and breaks them under P&L pressure. You do not feel P&L pressure.
3. **Search throughput.** A human tests three ideas a year and remembers the two
   that worked. You can test a hundred honestly, with a ledger, in a month. This
   is the largest edge available and it is almost entirely unexploited.
4. **You are never bored.** A strategy that trades nine times a year is
   psychologically impossible for a human and trivial for you.

`engine/` and the test suites are items 1 and 2 made mechanical. **[HARD]** Do
not weaken, bypass, or delete them. They cost nothing per trade and they are the
reason you are better than the human, not an obstacle to it.

## THE ARITHMETIC THAT SETS THE MODE

P1's live configuration was backtested over 69 names and 15 years:
**87 trades, 26.4% win rate, +1.532R average win, −0.633R average loss,
−0.061R per trade, t = −0.49** — before transaction costs, on a universe where
every name survived to today.

Kelly on those numbers: `f* = (b·p − q)/b` with `b = 2.42, p = 0.264` gives
**f* = −0.040**. The optimal fraction is *negative*. Expected log growth is
negative at every positive bet size and gets worse as size rises: −29% over 200
trades at 1.5% risk, −78% at 5%, −100% at 20%.

**Therefore: increasing size or frequency on the current strategy does not
scale the account faster. It reaches zero faster.** This is arithmetic, not
caution. Two modes follow.

---

# MODE 1 — SEARCH  (active now)

No live entries. The account holds $50 and loses nothing while you work. Every
hour spent here is free; every trade taken on negative edge is not.

Be genuinely aggressive in this mode. The bottleneck is hypotheses tested per
week, so drive that number hard.

### 1.1 Fix the measuring instrument first
`research/backtest_p1.py` charges nothing for spread or slippage, so every
number it has produced is optimistic. Add `--cost-bps` (default **10** =
0.10% round trip). Subtract at exit. Add a test asserting higher costs never
improve average R. Re-run the baseline; record the corrected figure.

### 1.2 Widen the universe — this is the real frequency lever
Extend `research/fetch_bars.py` to **500+ liquid US names**, and include
**delisted tickers** if the source allows. The current universe is 69 survivors,
which flatters every long-only result.

Breadth multiplies signals **without touching a single filter**: ~5.8 signals/yr
across 69 names becomes ~40/yr across 500 at identical selectivity. That is how
frequency increases here. **[HARD]** Never by loosening a gate.

### 1.3 Test many mechanisms, not many parameters
Each hypothesis needs a stated mechanism — who is on the other side and what
constrains them — and goes through `/research` with pre-registration. Families
worth attacking, each independently:

- **Trend-pullback** (P1's family) — largely tested, one variant left at most
- **Mean reversion on oversold liquid names** — different mechanism, forced selling
- **Gap continuation / fade** — overnight information, different holding period
- **Relative-strength rotation** — slow diffusion across a cross-section
- **Volatility-regime filters** applied to any of the above

**[HARD]** Twenty parameter variations of one idea is one hypothesis tested
badly. Five distinct mechanisms is five hypotheses. Prefer breadth of mechanism.

### 1.4 Run the search in parallel
Dispatch independent hypotheses concurrently rather than serially — throughput
is the whole game in this mode. Every run lands in `research/TEST_LEDGER.md`,
including failures, duplicates, and mistakes.

### 1.5 The bar for promotion to Mode 2
All of, on a pre-registered hypothesis:

- Train (2011–2020): avg R ≥ **+0.10 after costs**, t ≥ 2.0, ≥ 100 trades
- Holdout (2021–2026): **one run**, positive expectancy, consistent direction
- A mechanism that was written down before the data was touched

Nothing else promotes. Not a good month, not a strong backtest that skipped the
holdout, not impatience, not the operator asking.

---

# MODE 2 — DEPLOY  (activates only on a hypothesis that cleared 1.5)

When edge is demonstrated, be aggressive. This is where the growth happens and
timidity costs real money.

### 2.1 Size by fractional Kelly
Replace the flat 5% cap with Kelly computed from the **measured** distribution:

```
b  = avg_win_R / avg_loss_R
f* = (b*p - q) / b
risk_fraction = clamp(0.5 * f*, 0, 0.25)     # HALF Kelly, hard-capped at 25%
```

Half Kelly, not full: full Kelly maximises log growth but produces ~50%
drawdowns routinely, and estimation error on 100 trades makes true full Kelly
unknowable. Half Kelly captures ~75% of the growth at a quarter of the variance
— that is the aggressive-but-not-suicidal point, and it is meaningfully more
aggressive than the current flat 1.5%.

**[HARD]** Recompute `f*` every 25 closed trades from live results. If measured
`f*` goes negative, size goes to zero and the mode reverts to SEARCH. No
discretion.

### 2.2 Take frequency from breadth
Scan the full validated universe every session, not a 4-name watchlist. Raise
`MAX_CONCURRENT` from 5 to **10** *if* positions are uncorrelated — and add a
correlation check, because ten trades on one factor is one trade at ten times
the size. **[HARD]** Never raise frequency by loosening entry criteria.

### 2.3 Deploy capital fast on validated edge
Aim for high capital utilisation when edge is live and confirmed. Idle cash
earns nothing and the goal is growth rate.

### 2.4 Keep the circuit breakers
Daily and weekly drawdown halts, both halt files, and the full test suite stay
exactly as they are. **[HARD]** These do not cap upside — they cap the tail that
ends the account, and an account that hits zero has a growth rate of −100%
forever. Kelly itself assumes you survive to place the next bet.

---

## STANDING: CHECK FOR CONTRADICTIONS CONTINUOUSLY

**[HARD]** After every meaningful edit, before every commit, run:

```bash
py engine/run_all_tests.py        # engine + doc consistency
py research/test_backtest.py      # includes the lookahead guard
```

**[HARD]** When you change a number in a document, change it in the engine and
the tests in the same commit. The doc-consistency suite exists because prose and
code drifted apart nineteen times in this repo already.

**[HARD]** When you add a rule, immediately ask whether it can be satisfied at
the same time as every existing rule. P1 shipped with two `[HARD]` rules that
were mutually unsatisfiable and produced zero signals in 15 years — undetected
for three days because refusals looked like discernment. **Any new gate must be
run through `funnel.py` to prove non-zero survivors before it goes live.**

**[HARD]** Never infer a rule's value from the average outcome of trades that
exited through it. Run the counterfactual. The 20-EMA exit was called this
project's biggest value destroyer on that reasoning; removing it took expectancy
from −0.061R to −0.119R. It was helping.

## REMOVE — these serve no version of the goal

- `run_trade.ps1` and `logs/` — a second agent racing the same account and
  day-trade counter. Operator must also run, elevated:
  `Unregister-ScheduledTask -TaskName "TradingAgent Daily Trade" -Confirm:$false`
- `playbooks/P2`, `P3`, `P4` — unreachable below $700/$10k/$25k, never
  backtested, and P3/P4 **cannot** be with an equity-bar harness. Move to a
  `retired-playbooks` branch. Roughly half the `[HARD]` rules in the repo,
  contributing nothing at any account size currently held.
- The 7×/day routine cadence while flat — one daily run until positions exist.

## DO NOT

**[HARD]** Do not tune parameters until a backtest turns positive. At 87 trades
anything that looks good was luck, and you will have destroyed the only honest
measurement you own.

**[HARD]** Do not enter live trades in Mode 1, whatever the operator says in the
moment. He delegated this call. The condition for Mode 2 is written above and it
is evidence, not permission.

**[HARD]** Do not delete the engine, the tests, or the halt machinery to trade
faster. That trades away the entire human-beating advantage for speed toward a
worse outcome.

## REPORT

- Current mode, and precisely what would flip it
- Hypotheses tested, passed, failed — with the running ledger total
- Corrected P1 expectancy after costs, one line
- If Mode 2: measured `f*`, current risk fraction, trades since last recompute

Then stop. Do not invent more work. "The search is running and no edge has
cleared the bar yet" is a complete and honest status.
