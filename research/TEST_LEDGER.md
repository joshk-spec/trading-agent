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
