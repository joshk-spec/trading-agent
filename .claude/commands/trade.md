---
description: Run one full autonomous trading session against the Agentic account
---

Execute one complete trading session. Follow `CLAUDE.md` exactly. Every rule
marked **[HARD]** is a precondition, not a guideline.

## Phase 1 — Pre-flight (§3)

0. **Run the test suite first:** `py engine/run_all_tests.py` (73 tests). Any
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
4. **Run the engine for tier, halts, and budget — do not reason these out:**
   ```bash
   py engine/risk_engine.py preflight \
     --account <total_value> --session-open <marks> --week-open <marks>
   ```
   Report its output verbatim: tier, playbooks live, max risk per trade, whether
   PDT applies, and any halt reasons.
5. Count day trades via `risk_engine.count_day_trades()` against
   `state/day_trades.json`. Never count them by reading the journal.
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
limit price → **size via the engine** (`size-equity` / `size-option` / `size-csp`)
→ re-verify all [HARD] rules per §6 step 5, including `MAX_SYMBOL_EXP` summed
across equity and options in that underlying → `review_*_order` → place → confirm
fill → **for equity entries, place the resting protective stop-limit order (§6
step 9), or record why one couldn't be placed** → journal (record the engine's
`risk_pct`, `binding_constraint`, and the broker stop's status) → update state.

**[HARD]** Any quantity in an order payload must have come from the engine. If you
find yourself typing a share count or contract count you calculated yourself,
stop and run the engine.

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
