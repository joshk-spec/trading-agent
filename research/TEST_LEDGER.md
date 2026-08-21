# Test ledger

Every backtest run, including mistakes, duplicates, and runs you disliked. The
point is to make the multiple-comparisons problem visible — a curated ledger is
worse than none.

**Holdout budget used: 1 / 3.** After three, the 2020–2026 period is burned and
no further out-of-sample claim can be made from it.

**Train tests run: 20.** Divide your significance threshold by this number, or
state plainly that you have not. At 20 tests, α=0.05 Bonferroni ⇒ **|t| > 3.02**.
No result in this project has ever exceeded |t| = 1.87.

| # | date | set | what varied | result | verdict |
|---|---|---|---|---|---|
| — | 2026-08-21 | full period | P1 as written, target=prior_high | 0 signals / 15yr | **cannot execute** |
| — | 2026-08-21 | full period | P1, target=measured_move, intraday stop | 87 trades, −0.031R, t=−0.27 | no edge |
| — | 2026-08-21 | full period | P1, target=measured_move, close stop | 87 trades, −0.061R, t=−0.49 | no edge |
| 1–5 | 2026-08-21 | train | ema_exit ∈ {off,2,3,4,5} | best "off" −0.103R | see holdout #1 |
| H1 | 2026-08-21 | **holdout** | same 5 configs | ranking **inverted**: "off" worst (+0.077R), current rule best (+0.161R) | rule left unchanged |
| 6–20 | 2026-08-21 | train | 15 single-gate relaxations (`gate_study.py`) | none met pre-declared advancement criteria; max abs t = 1.87 | nothing advanced |
| — | 2026-08-21 | — | gate study holdout | **not consulted** — no variant qualified | budget preserved |

The first three rows predate the train/holdout protocol: they used the full
period with no split, so they cannot support an out-of-sample claim. They are
recorded because they happened.

Row H1 is the project's cleanest lesson: an in-sample "improvement" that
reversed sign out of sample. Acting on the train result alone would have made
the live rule worse. It is also the only holdout consultation so far — the gate
study deliberately spent none, because its pre-declared advancement gate
(≥3× trades AND avg R ≥ 0) admitted nothing.

**Standing conclusion:** 20 train tests and 1 holdout consultation have produced
no evidence of edge in P1 in any configuration, and no configuration approaches
the corrected significance threshold. Further variants tested against this same
1,000 name-years should be assumed to be finding noise.

---

## 2026-08-21 — instrument corrected, universe widened

Two changes to the measuring apparatus, not to any strategy.

**Costs.** `backtest_p1.py` charged nothing for spread or slippage, so every
number above was optimistic. `--cost-bps` now defaults to **10 = 0.10% round
trip**, charged once per position (not per partial exit), with a test asserting
higher costs can never improve a result. On the original 69-name universe this
moved P1 from −0.031R to **−0.079R**: costs alone were larger than the entire
previously-reported loss.

**Universe: 69 → 534 names.** Breadth is the only legitimate frequency lever —
identical selectivity across ~7× the names, with no gate touched. Signals went
5.8/yr → **32.7/yr**; the sample went 87 → **491 trades**.

**Delisted names are unavailable and the bias is therefore permanent.** Tested,
not assumed: the data source returns *zero* bars for TWTR, FRC, SIVB, ATVI,
CERN and XLNX. Every result here excludes companies that failed, which flatters
a long-only strategy. A negative result on this universe is stronger than it
looks.

### P1 final measurement (534 names, 15y, 10bps)

| | value |
|---|---|
| trades | **491** |
| win rate | 25.3% |
| avg win / avg loss | +1.430R / −0.593R |
| **average R** | **−0.082R** |
| t | **−1.74** |
| **95% CI on true edge** | **[−0.174R, +0.010R]** |
| max drawdown | −49.9R |

**This is decisive, and it is why breadth mattered.** At 87 trades the interval
was [−0.254R, +0.192R] — wide enough to contain the +0.10R promotion bar, so
"unproven" was the honest verdict. At 491 trades the upper bound is **+0.010R**,
and the bar sits **1.9 standard errors above** the best case the data permits.
P1 is no longer unproven. It is excluded.

**P1 is closed. No further variants of it will be tested** — 20 tests against
this dataset is already past the point where a positive result would mean
anything, and the mechanism has now been measured three independent ways
(unexecutable as written; no edge when fixed; no gate relaxation recovers it).

**Holdout budget: still 1 / 3.** The two changes above are instrument
corrections applied to the full period, not hypothesis tests, and spent no
holdout.

---

## 2026-08-22 — H001 withdrawn, unrun

Mean reversion with a 2.5×ATR stop. Withdrawn before execution: the operating
mandate is explicit that a tight stop converts mean reversion's edge into its
main loss source. A changed stop is a different hypothesis, so it was replaced
rather than amended. **No holdout spent, no train run.**

## 2026-08-22 — H002 short-term reversal (the P5 vehicle), TRAIN

Pre-registration: `research/preregistered/002_short_term_reversal.md`, committed
before `backtest_mr.py` was written. Spec taken verbatim from the mandate:
RSI(2)<5 above the 200-SMA, enter next open, exit next open once close > SMA(5),
10-session time stop, −15% disaster stop, **no tight stop**.

**TRAIN 2011-2020, 534 names, 10bps round trip:**

| | value |
|---|---|
| trades | **16,604** |
| win rate | 65.5% |
| avg return/trade after costs | **+0.274%** |
| average R (1R = 15% of entry) | **+0.0183R** |
| avg hold | 3.8 sessions |
| max drawdown | −10.9R |
| exits | reverted 96.9%, disaster 1.6%, time stop 1.5% |

**Significance, corrected for clustering.** Signals fire together on
market-wide selloffs (median 5 trades/day, max 110), so the naive t treats one
bet as many:

| grouping | n | avg R | t |
|---|---|---|---|
| naive, per trade | 16,604 | +0.0183 | **+9.91** |
| clustered by entry date | 1,940 days | +0.0135 | **+3.47** |
| clustered by month | 121 months | +0.0320 | **+3.99** |

74% of months positive. The effect survives the correction — t = 3.47 clusters
still clears both the 2.5 bar and a Bonferroni threshold for the project's ~22
tests (|t| > 3.0).

**VERDICT: FAILS the pre-registered bar.**

| criterion | required | got | |
|---|---|---|---|
| avg R | ≥ +0.05 | +0.0183 | **FAIL** |
| t | ≥ 2.5 | +3.47 clustered | PASS |
| trades | ≥ 500 | 16,604 | PASS |

**No holdout spent** — `backtest_mr.py` refuses `--holdout` when TRAIN fails,
so the budget stays at 1/3.

**This is a failure of magnitude, not of existence.** The edge is real,
robust to clustering, and economically non-trivial (+0.274%/trade over a 3.8
day hold). It does not reach a bar whose denominator I chose myself — see the
open question in FINDINGS.md. I am not restating that bar while holding the
result; that decision is the operator's.

**Running total: 21 train runs, 1 holdout use of 3.**

### CORRECTION 2026-08-22 — the numbers above were wrong in two ways

A code review found two defects that materially inflated the H002 result. Both
were verified independently before fixing. **The corrected result is worse and
changes the conclusion.**

**1. Max drawdown was computed in symbol order, not chronological order.**
`run()` appends trades symbol-by-symbol, so the cumulative-R loop walked AAPL's
entire decade, then AA's — a symbol-ordered sequence, not an equity curve.
Published −10.9R; actual **−94.3R** unconstrained. `backtest_p1.py` had the
identical defect (P1's −49.9R → **−61.2R**).

**2. No portfolio constraint — the 16,604 trades were not executable.**
The specification says "equal weight across MAX_CONCURRENT slots" and the
backtest booked every signal on every symbol: **median 17 and peak 228
simultaneous positions**, with 52% of days exceeding even 15 slots. The average
was taken over a portfolio nobody could run.

### H002 CORRECTED — 15 slots, the mandate's MAX_CONCURRENT

| | unconstrained (wrong) | 15 slots (executable) |
|---|---|---|
| trades | 16,604 | **5,806** |
| avg %/trade after costs | +0.274% | **+0.154%** |
| average R | +0.0183 | **+0.0102** |
| clustered t | +3.47 | **+2.57** |
| max drawdown | −10.9R (wrong) | **−34.4R** |

The slot cap roughly **halves** the per-trade edge, because the constraint bites
hardest exactly when the mechanism pays most — during market-wide selloffs,
when far more signals fire than there are slots to hold them.

**Slot-allocation rule is not load-bearing** (it is a free parameter, so all
three were run rather than the best one quoted): most-oversold-first +0.0102,
random +0.0105, alphabetical +0.0113. Arbitrary ordering does marginally
*better* than picking the most oversold.

### The economic verdict, which is the one that matters

| | |
|---|---|
| account return, 15 slots, 2011-2020 | **+59.4%** (+4.77%/yr) |
| SPY buy-and-hold, same window | **+194.3%** (+11.40%/yr) |
| capital utilisation | 9.5 of 15 slots (63%) |

**It loses to the index by more than half.** The mandate's own standard is
"beating a savings account is not the bar; beating buying the index is." On
TRAIN — with survivorship bias flattering it, and before the disaster stop
proves unenforceable at $50 — short-term reversal returns 4.8%/yr against SPY's
11.4%.

**VERDICT: FAILS.** avg R +0.0102 against a +0.05 bar (5× short). Clustered t
+2.57 scrapes past 2.5 but does **not** clear the Bonferroni threshold (~3.0)
for this project's 22 tests. **No holdout spent — budget remains 1/3.**

### Risk-adjusted check — no rescue there either

Compounded daily, capital-weighted:

| | total | CAGR | max drawdown | utilisation |
|---|---|---|---|---|
| SPY buy-and-hold | **+194.3%** | +11.40%/yr | −34.1% | 100% |
| MR, 15 slots | +76.0% | +5.82%/yr | −29.5% | 63% |
| MR, 30 slots | +60.9% | +4.87%/yr | −21.7% | 51% |

Return per unit of drawdown: SPY **0.33**, MR-15 **0.20**, MR-30 **0.22**. The
index dominates on both axes — more return AND more return per unit of pain.
There is no risk-adjusted framing that rescues this specification, and adding
slots lowers drawdown only by lowering return roughly in proportion.

**H002 is closed.** Dominated by buy-and-hold. No holdout spent; budget 1/3.

### Structural note for whatever is tested next

Both mechanisms measured so far (P1 trend-pullback, H002 reversal) are
**long-only, partially invested, and in the same asset class as the benchmark**.
MR sits in cash 37-49% of the time, so it must generate large alpha on the
invested half merely to match an index that is invested 100% of the time. That
is a structural handicap, not a property of either mechanism.

The one untested family that does not carry it is **cross-sectional momentum
(CAMPAIGN H1)**: rank the universe, hold the top decile, rebalance monthly —
fully invested at all times, no cash drag, and the most replicated anomaly in
equities. If anything here is going to beat the index, that is where to look.

