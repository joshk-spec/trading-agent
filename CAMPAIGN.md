# Research campaign — find an edge or prove there isn't one

Paste into Claude Code (Opus) from the repo root. Runs under `SCALE_MANDATE.md`
Mode 1. Trading stays halted for the duration; the account loses nothing while
this runs, so the only cost is time you are not spending anyway.

---

## MISSION

Test six mechanisms. Each gets pre-registered, run on train, and — only if it
passes — one shot at the holdout. Report what survives. If nothing does, say so
and stop.

**[HARD]** Do not lower the promotion bar because results disappoint or because
the operator is impatient. A campaign that concludes "no edge here" in two weeks
is a success; it saves years of feeding capital into something that does not
work. The whole point of doing this at $50 is that being wrong is free.

## WHAT IS ALREADY KNOWN — do not retread

- **Trend-pullback (P1)**: measured-move target, intraday stop, 69 names,
  15 years → 87 trades, **−0.061R, t = −0.49**, before costs. No edge.
- **20-EMA exit**: counterfactual tested. Removing it → −0.119R. It helps. Leave it.
- **Prior-high target**: geometrically unsatisfiable, 0 signals in 15 years.
- The backtest models **no transaction costs**. Fix that first (below); every
  historical number is optimistic until you do.

## STEP 0 — PREPARE THE INSTRUMENT

Nothing below is believable until these two are done.

1. **Costs.** Add `--cost-bps` to `research/backtest_p1.py`, default **10**
   (0.10% round trip), subtracted at exit. Add a test asserting higher costs
   never improve average R. Re-run the P1 baseline; record the corrected number
   in `research/FINDINGS.md` and the ledger.
2. **Universe.** Extend `research/fetch_bars.py` to **500+ liquid US names**, and
   include delisted tickers if the source permits. The current 69 are all
   survivors, which flatters every long-only result. Breadth is also the only
   legitimate way to raise trade frequency — same selectivity, more shots.

## THE SIX HYPOTHESES

Each has a real mechanism — a reason someone is on the other side at a
disadvantage. **[HARD]** Pre-register each in `research/preregistered/` and
commit before its first run.

**H1 — Cross-sectional momentum (12-1).** Rank the universe by trailing 12-month
return excluding the most recent month; hold the top decile, rebalance monthly.
*Mechanism:* underreaction to slow-diffusing information; the 1-month gap avoids
short-term reversal. The most replicated anomaly in equities — if nothing here
works, that is itself informative about your implementation.

**H2 — Post-earnings announcement drift.** Long the largest positive earnings
surprises, hold 60 days. *Mechanism:* analysts anchor on prior estimates and
revise too slowly; the price adjusts over weeks, not instantly. Needs earnings
dates — if unavailable, say so and drop H2 rather than substituting a proxy.

**H3 — Oversold mean reversion inside an uptrend.** Price above the 200-day SMA,
RSI(2) below 5, buy the close, exit above the 5-day SMA. *Mechanism:* forced and
panic selling transacts against liquidity providers who demand compensation.
Note this is the **opposite** trade to P1 — that is the point, not a conflict.

**H4 — Overnight vs intraday decomposition.** Measure close-to-open and
open-to-close returns separately across the universe. *Mechanism:* the overnight
risk premium is compensation for holding un-hedgeable gap risk. Not a strategy
yet — a measurement that tells you which half of the day carries the return, and
therefore which holding period is even worth testing.

**H5 — Volatility-regime overlay.** Take whichever of H1–H3 performs best and
gate it on VIX or realised-vol regime. *Mechanism:* trend and reversion have
opposite regime dependence; a filter that helps one should hurt the other, which
is a falsifiable prediction rather than a fitted parameter.
**[HARD]** Run H5 only after H1–H3 report. It is conditional by construction and
running it early turns it into parameter search.

**H6 — Gap fade.** Fade opening gaps beyond 2 standard deviations on liquid
names, exit same day. *Mechanism:* overnight overreaction to news in thin
pre-market liquidity. **[HARD]** Every trade is a day trade — PDT caps this at
3 per 5 business days under $25,000, so even a positive result is unusable at
current size. Test it for information, and record that constraint in the finding.

## PROTOCOL — per hypothesis

1. Pre-register: mechanism, exact rules, every parameter fixed, success and kill
   criteria. Commit before running.
2. Train **2011-01-01 → 2020-12-31** only. The holdout does not exist yet.
3. Run `funnel.py` alongside. **[HARD]** Any gate that zeroes out is the finding —
   report it and stop that hypothesis. That failure mode already cost this
   project three days.
4. Promotion bar, all required: **avg R ≥ +0.10 after costs**, **t ≥ 2.0**,
   **≥ 100 trades**.
5. Holdout **2021-01-01 → 2026-08-21**: one run, one shot, no adjust-and-retry.
   Maximum three hypotheses may ever touch it.
6. Log every run in `research/TEST_LEDGER.md` — including mistakes, duplicates,
   and runs you disliked. A curated ledger is worse than none.

**Run H1, H2, H3, H4 concurrently.** Throughput is the entire advantage you have
over a human here; a human tests three ideas a year and remembers the two that
worked. Do not serialise independent work.

## GUARDS — check continuously, not at the end

- `py engine/run_all_tests.py` and `py research/test_backtest.py` before every commit
- **[HARD]** Counterfactual, never conditional. To claim a rule helps, run the
  strategy with and without it and compare total expectancy. Never infer value
  from the average outcome of trades that exited through it.
- **[HARD]** No parameter tuning to reach the bar. Twenty variants of one idea is
  one hypothesis tested badly; the best of twenty is luck. If a variant is worth
  testing it gets its own pre-registration and its own ledger row.
- **[HARD]** t ≥ 2 is necessary, not sufficient. After twenty tests roughly one
  crosses it by chance. Divide the threshold by the ledger count or state plainly
  that you have not.

## STOP CONDITION

**[HARD]** If all six fail on train, stop. Write in `research/FINDINGS.md`:
*"Six mechanisms tested with pre-registration. None cleared the promotion bar.
No accessible edge demonstrated on daily US equity bars at this sample size."*

Do not then loosen the bar, widen the universe until something passes, or split a
dead hypothesis into variants. If nothing worked, the honest conclusion is that
nothing works here — not that the test was too strict.

## REPORT

- Corrected P1 expectancy after costs, one line
- Per hypothesis: mechanism, funnel survivors, train result, holdout if reached
- Ledger totals: train runs, holdout budget used of 3
- **The verdict**, in one of exactly two forms: the name of the hypothesis that
  cleared out-of-sample, or "no accessible edge demonstrated"

Then stop. Do not invent follow-on work. "The search ran and nothing cleared the
bar" is a complete and valuable result.
