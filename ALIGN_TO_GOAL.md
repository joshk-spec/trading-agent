# Prompt — align the codebase to the goal

Paste this whole thing into Claude Code from the repo root.

---

## THE GOAL

**Grow this account as much as possible, as safely as possible.**

Those two halves sound like they trade off. Right now they do not — they point
the same direction, and the whole of this task follows from understanding why.

Expected growth is maximised by deploying capital *only* into strategies with
demonstrated positive expectancy. Safety is maximised by not deploying capital
otherwise. When no strategy has demonstrated edge, "trade less" and "grow more"
are the same instruction. The account is at $50; the cost of waiting is
approximately zero, and the cost of trading a measured-negative strategy is not.

## THE DECISION RULE

A change to this repo qualifies **only** if it does one of:

- **(a)** increases expected return, supported by out-of-sample evidence
- **(b)** reduces the probability or size of a loss
- **(c)** reduces the cost or time of finding out whether an edge exists

Anything else — tidier prose, more rules, more tests of things already tested,
another consistency audit — does not qualify, however tempting. This project has
already spent three days on work that qualified under none of these. Do not add
to that.

**[HARD]** Before each change, name which of (a), (b), (c) it serves. If you
cannot, skip it and say so in the report.

## WHAT YOU MUST KNOW BEFORE TOUCHING ANYTHING

Read `research/FINDINGS.md` in full first. The load-bearing facts:

1. P1's live configuration — **measured-move target, intraday stop** — is
   precisely the configuration that was backtested over 69 names and 15 years.
   Result: **87 trades, −0.061R per trade, t = −0.49.** No edge, point estimate
   negative, and survivorship bias in the universe flatters that number.
2. The backtest models **zero** transaction costs. Real spread and slippage push
   every result further negative. The measured −0.061R is optimistic.
3. Findings 1 and 3 have already been fixed in `playbooks/P1_equity_momentum.md`.
   **P1 can now fire.** It could not before. That is a change from "inert" to
   "armed and pointed at a strategy measured to lose money slowly."
4. The 20-EMA exit was tested by counterfactual: removing it takes expectancy
   from −0.061R to **−0.119R** and drawdown from −12.0R to −16.5R. It is
   *helping*. Leave it alone. The earlier claim that it destroyed value came from
   reading the average of trades that exited through it — conditioning on
   outcome, not causation.
5. At $50 the account is T0. **Only P1 is reachable.** P2 unlocks at $700, P3 at
   $10,000, P4 at $25,000.

## THE CHANGES — in this order

### 1. Stop live trading until something has demonstrated edge — (b)

The highest-value action available, and the least intuitive.

Write `state/HALT` with a reason naming the measured expectancy and the date.
Do not delete the engine, the tests, the halt machinery, or the routine — this
is a safety catch, not a teardown, and it must be trivially reversible when
evidence arrives.

The system keeps reconciling, keeps journalling, keeps its state current. It
just does not open positions into a strategy whose measured expectancy is
negative. **That is not giving up on the goal; at t = −0.49 it is the only move
that serves it.**

### 2. Model transaction costs in the backtest — (c)

`research/backtest_p1.py` charges nothing for spread, slippage, or commission,
so every number it has ever produced is biased upward. Fix the instrument before
running another test with it.

Add a `--cost-bps` argument, default **10** (0.10% of entry, round trip, a fair
figure for liquid US large caps). Subtract it from every trade's R at exit.
Re-run the baseline and record the corrected number in `research/FINDINGS.md`
and `research/TEST_LEDGER.md`.

Add a test asserting that a higher `--cost-bps` never produces a *better*
average R. That is the invariant, and it is cheap to check.

### 3. Delete P2, P3, and P4 — (b) and (c)

Move them to a `retired-playbooks` branch, delete from `main`, and remove their
rows from CLAUDE.md §1 and §4.

Why this serves the goal rather than merely tidying: they are unreachable for
the foreseeable account size, none has ever been backtested, and **P3 and P4
cannot be backtested at all** with an equity-bar harness — they need options
data you do not have. They are roughly half the `[HARD]` rules in this repo and
most of its audit surface, and they contribute nothing to behaviour at any
account value you currently hold. Every future review of this codebase pays for
them.

Keep the tier system itself. Keep P1. Update the doc-consistency tests to match
the smaller set and confirm they still pass.

### 4. Cut the routine to once daily — (b)

The cloud routine `trading-agent-daily-session` fires seven times a day. P1
entries only ever trigger off a prior session's close, and there are no open
positions to manage intraday. Six of seven runs are pure cost and pure
opportunity for something to go wrong.

Change the cron to a single run at **13:35 UTC** (9:35 ET). Note in
`CLAUDE.md` that the hourly cadence should return **only** when positions are
actually open and need intraday management.

### 5. Remove the second trading path — (b)

`run_trade.ps1` is disabled by an internal flag, but the Windows scheduled task
`TradingAgent Daily Trade` is still registered and still firing. One edited
variable away from two agents racing the same account, the same `state/*.json`,
and the same day-trade counter — where the penalty is a 90-day PDT restriction.

Delete `run_trade.ps1` and `logs/`. Leave the operator a one-line instruction to
run in an **elevated** PowerShell, because it cannot be done without admin:

    Unregister-ScheduledTask -TaskName "TradingAgent Daily Trade" -Confirm:$false

### 6. Point the primary loop at research — (c)

Install `/research` (`.claude/commands/research.md`) as the main activity while
trading is halted. Add a short section to `README.md` stating plainly: the
current state is *halted, searching for edge*, and the condition for resuming is
a hypothesis that passed a pre-registered out-of-sample test — not a good week,
not a promising backtest, not impatience.

## WHAT NOT TO DO

**[HARD]** Do not tune P1's parameters to make the backtest positive. With 87
trades, any parameter set that looks good was found by luck. If you want to test
a variant, it goes through `/research` with pre-registration — not into
`playbooks/`.

**[HARD]** Do not loosen any risk cap, widen any stop, or raise `MAX_RISK_TRADE`
to make positions larger. Position size is not the constraint. Edge is.

**[HARD]** Do not remove the 20-EMA exit. Tested. It helps.

**[HARD]** Do not add a new playbook, indicator, or strategy on intuition. Every
addition needs a mechanism and a pre-registered test first. This repo already
contains 1,200 lines of confident, well-tested rules that could not make money;
its problem has never been too few ideas.

**[HARD]** Do not run another consistency audit. Nineteen have been found and
fixed. The specification is not what is wrong.

## VERIFICATION

1. `py engine/run_all_tests.py` — all pass, including doc-consistency after the
   playbook deletions
2. `py research/test_backtest.py` — all pass, including the new cost invariant
3. `py research/backtest_p1.py --target-mode measured_move --cost-bps 10` —
   record the corrected expectancy
4. `py engine/risk_engine.py preflight --account 50 ...` — confirm it reports the
   halt
5. `git status` clean, changes committed with a message explaining which of
   (a)/(b)/(c) each change served

## REPORT

Finish with:

- Each change, and which of (a)/(b)/(c) it served
- Anything you skipped because it served none — and what it was
- P1's expectancy **after** costs, stated in one line
- The single condition that would justify resuming live trading, in one sentence

Then stop. Do not look for more work. If the honest answer is "the codebase now
serves the goal and the open question is whether any edge exists," say exactly
that and end the session.
