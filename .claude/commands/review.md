---
description: Weekly performance review — read-only, places no orders
---

Read-only. **Place no orders during this command under any circumstance.**

1. Read all `journal/*.md` entries from the trailing 7 days.
2. Pull `get_realized_pnl` and `get_pnl_trade_history` for the period.
3. Reconcile the journal against broker records. Flag any trade present in one
   and not the other — that is a §7 incident.

Compute and report:

- Trade count (closed), win rate, average win in R, average loss in R
- Expectancy in R, max drawdown, current tier and distance to the next
- Per-playbook breakdown — which are contributing, which are bleeding
- Rule violations: any [HARD] rule breached, with the journal reference

Then, per §10, state the statistical position plainly:

> Closed trades: N. At N < 30, results are **not statistically distinguishable
> from luck** in either direction. A 55%-edge strategy loses over its first 20
> trades about a third of the time; a zero-edge strategy shows a profit about
> half the time. Do not scale capital on this sample.

**[HARD]** Do not describe the system as working, validated, or profitable below
30 closed trades. Report raw numbers and let them be what they are.

Finish with the single highest-value change to consider — or "insufficient data
to justify any change," which is the correct answer early on.
