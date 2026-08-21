# P1 backtest — findings (2026-08-21)

Universe: 69 liquid US large/mid caps + SPY. Period: 2011-08-22 → 2026-08-21
(~1,000 name-years, 239,917 bar-days evaluated). Daily split-adjusted bars.

Reproduce:

```bash
py research/fetch_bars.py         # downloads bars into research/data/
py research/test_backtest.py      # 24 tests, incl. the lookahead guard
py research/backtest_p1.py --target-mode prior_high
py research/backtest_p1.py --target-mode measured_move
py research/funnel.py             # which gate eliminates what
py research/target_study.py       # why the reward:risk gate never passes
```

---

## Finding 1 — P1 as written cannot take a trade. Ever.

With the target read as a **prior high** (the playbook's first-listed reading),
the strategy produced **zero signals in 15 years across 69 names.** Not few —
zero.

The funnel isolates it exactly. Of 239,917 bar-days, **341 clear every single
P1 condition except reward:risk**, and **0 clear reward:risk**:

| gate | survivors |
|---|---|
| bars evaluated | 239,917 |
| … SPY regime, trend structure, within 8% of 252d high | 66,304 |
| … pullback 3–10% into the 20-EMA on declining volume | 14,271 |
| … RSI trough 40–55 and turned up | 5,269 |
| … outperformed SPY over 20 sessions | 2,437 |
| … close above prior high on ≥20d average volume | 341 |
| … stop ≤ 12% of entry | 341 |
| **… reward:risk ≥ 2.0** | **0** |

**The mechanism is geometric, not statistical.** Measured at the moment the
trigger fires, on those 341 candidates:

```
median room UP to the 60-day high     2.09% of entry
median room UP to the 252-day high    2.60%
median room DOWN to the stop          4.01%
```

The entry trigger requires *a close above the prior session's high* — the
recovery has already happened. By the time P1 is allowed to buy, price has
climbed back to within ~2% of the old high, while the structural stop is still
parked at the pullback low ~4% below. That is a reward:risk near **0.5**, and
no amount of waiting changes it: the best single observation in 15 years was
1.67 against the 60-day high.

To clear 2.0 against the 252-day high, the stop would have to sit within
**1.30%** of entry. The playbook's own stop rule — `min(pullback low,
entry − 2×ATR)` — produces **4.01%**.

Two `[HARD]` rules are therefore mutually unsatisfiable: *"minimum
reward:risk 2.0"* and *"compute the target from real structure — prior high"*,
given the 8%-from-highs filter and the post-recovery entry trigger. The live
agent refusing every candidate is those rules working exactly as written.

## Finding 2 — under the only reading that permits trading, there is no edge

P1 also allows a **measured move** target. Projecting the pullback's depth above
the swing high is the only admissible reading that clears 2.0 with any
regularity (32.6% of candidates; a 2× projection clears 97.9%, which is plainly
choosing a target to beat the test — the inversion the playbook forbids).

Backtested with measured-move targets, 87 trades over 15 years:

| | broker stop (intraday) | close-based stop |
|---|---|---|
| trades | 87 | 87 |
| win rate | 19.5% | 26.4% |
| **average R** | **−0.031R** | **−0.061R** |
| total | −2.7R | −5.3R |
| avg win / avg loss | +1.94R / −0.51R | +1.53R / −0.63R |
| max drawdown | −11.9R | −12.0R |
| t-statistic | −0.27 | −0.49 |

**No edge is demonstrated.** Both point estimates are negative and both
t-statistics are near zero, so the honest statement is not "P1 loses money" but
**"15 years of data cannot distinguish P1 from a coin flip, and what signal
there is points slightly negative."**

Two secondary observations:

* **Frequency is 5.8 trades/year across 69 names** (0.08 per name per year).
  Even working perfectly, this is a rare-signal strategy — it would sit idle
  most weeks by design.
* **The 20-EMA exit is the main destroyer of value**: 42–53 of the 87 trades
  exit that way at an average of −0.36R, while stop exits average *positive*
  (+0.27R, because the breakeven and 1.5-ATR trails move the stop up first).
  If anything here is worth re-examining first, it is that exit.

## Finding 3 — the two documents disagree about what a stop is

P1's exit table says *"Stop hit (**close** below stop_price)"*. CLAUDE.md §6
step 9 now rests a **stop-limit** at the broker, which triggers **intraday on
any touch**. These are different exits — a wick through the stop that closes
back above it is a full loss under one and a non-event under the other. The
table above quantifies it: same 87 signals, different win rates (19.5% vs
26.4%) and different average R. This needs to be resolved deliberately, not
left as an accident of which document is read.

---

## Biases, stated plainly

* **Survivorship — the big one, and it flatters these numbers.** Every symbol
  still trades today; names that were liquid in 2011 and later collapsed or
  were delisted are absent. A long-only trend strategy looks better than
  reality on such a universe. The result is negative *despite* this.
* **Earnings exclusion not modelled** (dates unavailable in bar data). Live, P1
  refuses names with earnings in the holding horizon, which removes some large
  gap losses. Biases these results **down**.
* **No spread, slippage, or commission.** Biases results **up**.
* **Portfolio caps not applied** — MAX_CONCURRENT and the exposure limits
  reduce how many of these you could hold at once but do not change per-trade
  edge, which is what is measured here.
* **One position per symbol at a time**, matching live behaviour.

## What this does not say

It does not say the underlying idea is worthless. Trend-pullback continuation
is a real, widely-documented effect. What it says is that **this particular
parameterisation, on this universe, over this period, shows no measurable
edge — and cannot execute at all as literally written.**

## Decisions this leaves open (all are the operator's, not the agent's)

1. Resolve the target definition in `playbooks/P1_equity_momentum.md`. As
   written, P1 is unexecutable. It needs to name one reading.
2. Resolve close-based vs intraday stops between the playbook and §6 step 9.
3. Re-examine the 20-EMA exit — the single largest source of negative R.
4. Decide whether to keep P1 at all, given no demonstrated edge, before adding
   capital against it.
