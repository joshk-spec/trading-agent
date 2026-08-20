---
description: Run one full autonomous trading session against the Agentic account
---

Execute one complete trading session. Follow `CLAUDE.md` exactly. Every rule
marked **[HARD]** is a precondition, not a guideline.

## Phase 1 — Pre-flight (§3)

0. **Run the test suite first:** `py engine/run_all_tests.py` (108 tests). Any
   failure ⇒ do not trade, report the failure. The risk math must be verified
   before money moves.
1. Check both halt files. `state/HALT` present ⇒ reconcile, report, **exit**
   (operator-only; you may never clear it). `state/HALT_TODAY` present ⇒ if its
   date is today, exit; if the date is older, delete it and continue.
2. Reconcile from the broker — `get_portfolio`, `get_equity_positions`,
   `get_option_positions(nonzero=true)`, `get_equity_orders`, `get_option_orders`.
   The broker is the only source of truth.
3. Diff against `state/positions.json`. Any unexplained discrepancy is an
   incident under §7 — investigate before proceeding. Then **rewrite
   `state/positions.json` from the live broker data** (schema in CLAUDE.md
   §2.1) before sizing anything — the sizing CLI reads this file by default to
   enforce `MAX_SYMBOL_EXP`/`MAX_CONCURRENT`, so a stale file makes those caps
   silently under-count.
4. **Set today's marks, then run the engine for tier, halts, and budget — do not
   reason these out.** If `state/marks.json` `session_open_date` is not today,
   set `session_open_value` to the live account value and `session_open_date` to
   today first; same for `week_open_*` at the first run of a week (§2.2).
   ```bash
   py engine/risk_engine.py preflight --account <total_value> \
     --session-open <value> --session-open-date <YYYY-MM-DD> \
     --week-open   <value> --week-open-date   <YYYY-MM-DD>
   ```
   Report its output verbatim: tier, playbooks live, max risk per trade, whether
   PDT applies, and any halt reasons. **Both mark flags default to `0.0`, a
   missing mark silently evaluates nothing, and a stale or undated mark measures
   against the wrong baseline — so check `checks_skipped` in the output.
   Non-empty ⇒ a [HARD] halt rule could not be verified ⇒ do not trade
   (§2.0/§2.2); fix `state/marks.json` and re-run preflight.** `halt: false` with
   a non-empty `checks_skipped` is not an all-clear.
5. **Count day trades with the engine's own command** — never by reading the
   journal, and never with an ad-hoc script:
   ```bash
   py engine/risk_engine.py day-trades --account <total_value>
   ```
   It reads `state/day_trades.json` and reports `used`, `available`, and
   whether PDT applies. A 4th day trade under $25k restricts the account for
   90 days, so `available` is a hard budget, not a guideline.
7. List anything expiring within 2 sessions — each needs a decision this run.

Report the pre-flight block before doing anything else.

## Phase 2 — Manage existing positions (§5)

Before looking at a single new idea. For each open position: live quote, P&L,
playbook exit conditions, time stops, thesis invalidation. Act and journal.

If a stop tightened this run (breakeven trail, ATR trail, etc.), cancel the
resting broker stop-limit order and replace it at the new stop_price (§5, §6
step 9). Verify every open whole-share position still has a protective stop
resting at the broker; if one doesn't (never placed, got cancelled, fractional
quantity), say so explicitly in the journal — don't let it pass silently.

## Phase 3 — Scan for new entries (§4)

Only playbooks unlocked at the current tier. Read the playbook file — do not
work from memory. For each candidate, verify every criterion explicitly and show
the check. A candidate failing any **[HARD]** rule is dropped without further
analysis.

If nothing qualifies, say so and move on. Zero-trade sessions are normal and
expected, particularly at T0.

## Phase 4 — Execute (§6)

Full sequence per order: live quote → `risk_engine.check_option_liquidity()` →
limit price → **size via the engine** (`size-equity` / `size-option` / `size-csp`;
pass `--target` on P1 so the engine enforces the 2.0 minimum reward:risk)
→ re-verify all [HARD] rules per §6 step 5, including `MAX_SYMBOL_EXP` summed
across equity and options in that underlying → `review_*_order` → place → confirm
fill → **for equity entries, place the resting protective stop-limit order (§6
step 9), or record why one couldn't be placed** → journal (record the engine's
`risk_pct`, `binding_constraint`, and the broker stop's status) → update state.

**[HARD]** Any quantity in an order payload must have come from the engine. If you
find yourself typing a share count or contract count you calculated yourself,
stop and run the engine.

**[HARD]** Before any P1 entry, check the engine's own verdict flags — a result
can be `ok: true` while a [HARD] rule went unchecked. Both flags are the
engine's answer, never your own read of the numbers:
- `rr_verified: false` ⇒ you did not pass `--target`, so the 2.0 minimum
  reward:risk was never tested. Do not enter. Re-run with the structural target.
- `stop_eligible: false` ⇒ the quantity is fractional, so **no broker-side stop
  can be placed** (§6 step 9) and the position has no intraday protection
  between runs. Journal `Broker stop: none — fractional quantity`. Never round
  the quantity up to make it `true` — that breaches `MAX_POS_NOTIONAL`.

## Phase 5 — Close out

1. Cancel unfilled orders not explicitly intended to rest.
2. Update `state/positions.json`, `state/marks.json`, `state/day_trades.json`.
3. Write `journal/YYYY-MM-DD.md`.
4. Print the §11 session report.

## Standing reminders

- You may not clear `state/HALT`. Only the operator can. `state/HALT_TODAY` may
  be cleared only when its date stamp is older than today.
- If the engine and `CLAUDE.md` disagree on any number, **the engine wins** and
  the disagreement is a §7 incident — halt and report it.
- Skipping a trade is always available and frequently correct.
- If something occurs that `CLAUDE.md` does not cover: **halt and ask.** You
  execute a specified system; you do not invent one at runtime.
