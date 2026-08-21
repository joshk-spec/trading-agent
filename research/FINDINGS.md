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

---

# Resolutions applied 2026-08-21

## 1. Target definition — FIXED

`playbooks/P1_equity_momentum.md` now names exactly one rule:

```
target = swing_high + (swing_high - pullback_low)     # measured move
```

The old menu ("prior high, measured move, or a resistance level") made P1
unexecutable under its most natural reading. Pinned by
`test_f20_p1_names_exactly_one_target_rule` and
`test_f21_the_unexecutable_target_reading_stays_documented`. The old reading
remains reproducible with `--target-mode prior_high`, which still yields 0
signals in 15 years.

## 2. Stop model — FIXED

P1's exit table now reads **"Stop touched intraday (`low <= stop_price`)"**,
matching the resting stop-limit that CLAUDE.md §6 step 9 places at the broker.
§6 step 9 is stated as the authority on what "stop hit" means, and the
fractional-share case — where no broker order can exist and the stop is
therefore evaluated at the next scheduled run — is called out explicitly in
both documents. Pinned by `test_f19_p1_stop_is_intraday_not_close_based`.

## 3. The 20-EMA exit — DELIBERATELY NOT CHANGED

This was the tempting one, and the data says leave it alone. Tuned on
2011-2019 only, then validated on 2020-2026 without further adjustment:

| `ema_exit` | in-sample avg R | out-of-sample avg R |
|---|---|---|
| off | **−0.103 (best)** | +0.077 (**worst**) |
| 2 (current) | −0.173 | **+0.161 (best)** |
| 3 | −0.309 | +0.129 |
| 4 | −0.230 | +0.117 |
| 5 | −0.195 | +0.114 |

**The in-sample ranking inverts out-of-sample.** Disabling the exit looks best
on 2011-2019 and is worst on 2020-2026. Changing the rule on the strength of
the in-sample result would have been curve-fitting a 49-trade sample and would
have made the recent period worse. No configuration reaches |t| > 2.3 in either
window, so none of them is distinguishable from noise. The rule stays as-is.

The observation that prompted this — that 20-EMA exits average −0.36R while
stop exits average +0.27R — turns out to be selection, not causation: "stop"
includes every trade that reached +1R or +2R and trailed out a winner, so that
bucket is positive by construction.

## What is still open

**The edge question. Fixing executability did not create an edge.** With both
fixes in force the strategy is unchanged in expectancy: 87 trades, −0.031R per
trade, t = −0.27. P1 can now *run*; there is still no evidence it *works*, and
the sample cannot rule out a small edge in either direction. The split above
also shows a negative first half and a positive second half, neither
significant — consistent with regime dependence, or with noise.

That decision — whether to keep P1, and whether to add capital against it —
remains the operator's and is not made better by more tinkering with the same
1,000 name-years.
