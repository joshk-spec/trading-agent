# Test ledger

Every backtest run, including mistakes, duplicates, and runs you disliked. The
point is to make the multiple-comparisons problem visible — a curated ledger is
worse than none.

**Holdout budget used: 0 / 3.** After three, the 2021–2026 period is burned and
no further out-of-sample claim can be made from it.

**Train tests run: 0.** Divide your significance threshold by this number, or
state plainly that you have not.

| # | date | set | what varied | result | verdict |
|---|---|---|---|---|---|
| — | 2026-08-21 | train+holdout | P1 as written, target=prior_high | 0 signals / 15yr | **cannot execute** |
| — | 2026-08-21 | train+holdout | P1, target=measured_move | 87 trades, −0.061R, t=−0.49 | no edge |
| — | 2026-08-21 | train+holdout | P1, measured_move, ema_exit off | 86 trades, −0.119R, t=−0.72 | worse — exit was cutting losers |

The three rows above predate this protocol: they used the full period with no
train/holdout split, so they cannot support an out-of-sample claim. They are
recorded because they happened, and because the third one is the project's
cleanest example of why a conditional average is not a causal claim.
