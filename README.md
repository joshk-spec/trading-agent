# Autonomous Trading Agent — Setup

A capital-tiered, rule-bounded trading system for Claude Code, operating the
Robinhood Agentic account `793973603` (Level 2, single-leg only).

## Install

```bash
# 1. Unzip wherever you keep projects, and cd into it
cd ~/trading-agent

# 2. Add the Robinhood MCP server (verified endpoint)
claude mcp add robinhood-trading --transport http \
  https://agent.robinhood.com/mcp/trading

# 3. Authenticate
claude
> /mcp                    # select robinhood-trading, complete OAuth in browser

# 4. Confirm it connected and can see the right account
> /mcp                    # status should read "connected"
> which accounts can you see?
```

The MCP is added at **local scope** by default — registered to this directory
only, in `~/.claude.json`. That is what you want here: the trading tools should
not be loadable from unrelated projects. Do not use `--scope user`.

Robinhood's agent has read access across your accounts but can only *place
trades* in the Agentic account (`793973603`). The constitution restates that as
a [HARD] rule so the agent never attempts an order elsewhere.

`CLAUDE.md` loads automatically every session. The playbooks in `playbooks/`
are read on demand during a run — this keeps the always-loaded context small
while the detailed rules stay available.

## Run

```
/trade      # one full trading session
/review     # weekly read-only performance review
```

## Kill switch

```powershell
"manual halt" | Out-File state/HALT     # stops all trading immediately
Remove-Item state/HALT                  # only you can clear it
```

There are two halt files and they are not the same:

| File | Written when | Cleared by |
|---|---|---|
| `state/HALT` | Weekly drawdown breach, or any §7 condition | **You, by hand. Never the agent.** |
| `state/HALT_TODAY` | Daily drawdown breach | The agent, next session, once its date stamp is stale |

The agent is forbidden from clearing `state/HALT` or writing itself an exception.
If it halts on its own, read the reason before clearing.

## Verify the risk math

```powershell
py engine/run_all_tests.py
```

109 tests, no dependencies beyond stdlib Python.

(Use `py` on Windows. On macOS or Linux the command is `python3`.) They pin every constitutional
number — tier boundaries, the 5%/25%/30%/40% caps, the Minimum Viable Unit rule,
PDT window arithmetic, drawdown triggers, and the liquidity gates against real
quotes. The agent is required to run these before its first order each session
and to refuse to trade if any fail.

`engine/risk_engine.py` is the single source of truth for every number that
decides how much money is at stake. The agent shells out to it rather than doing
arithmetic itself — position size, tier, exposure, drawdown, and day-trade counts
all come from tested code. **If the documents and the engine ever disagree, the
engine wins** and the agent must halt and report it.

## What is active right now

**MODE: SEARCH — no live entries.** Account value is **$50**, funded, flat.

P1, the only playbook, has been measured over 534 names and 15 years after
10bps round-trip costs: **491 trades, −0.082R per trade, t = −1.74, 95% CI
[−0.174R, +0.010R]**. The bar for deploying capital is +0.10R after costs,
which lies above the upper bound of that interval — so this is not "unproven",
it is excluded. Kelly on the measured distribution is negative, meaning every
positive bet size has negative expected log growth. The account therefore
holds cash and loses nothing while the search runs.

Mode flips to DEPLOY only when a pre-registered hypothesis clears the bar in
`research/TEST_LEDGER.md`: train avg R ≥ +0.10 after costs, t ≥ 2.0, ≥100
trades, then one holdout run that confirms. Nothing else promotes.

The cloud routine `trading-agent-daily-session` runs **once daily** while flat
(it reconciles, journals, and confirms nothing has drifted). The local Windows
task and `run_trade.ps1` are **deleted** — they drove a second agent against
the same account and the same day-trade counter. To remove the scheduled task
itself, run elevated:
`Unregister-ScheduledTask -TaskName "TradingAgent Daily Trade" -Confirm:$false`

| Tier | Account value | Unlocks |
|---|---|---|
| **T0** | < $700 | P1 equity momentum only |
| T1 | $700 – $2,500 | + P2 swing options, reduced size |
| T2 | $2,500 – $10,000 | + P2 at full size |
| T3 | $10,000 – $25,000 | + P3 wheel |
| T4 | ≥ $25,000 | + P4 0DTE, PDT restriction lifts |

At T0 the agent will trade fractional shares and will decline every options
setup it finds. That is correct behavior, not a malfunction — see §2.3 of
`CLAUDE.md` for why, with the arithmetic.

**At $50 no position can carry a broker-side stop.** Sizing caps a position at
25% of the account ($12.50), which is under one share of most liquid names, and
Robinhood rejects stop orders on fractional quantities. The engine reports this
as `stop_eligible: false`. Those positions have **no intraday protection** — a
crash between scheduled runs is only caught at the next run. Whole-share
positions, and the resting stops that protect them, begin around a $200
account on a ~$15 stock.

## Before the first live run

1. **Paper-run it.** Add `state/HALT` and run `/trade` for a week. The agent
   still does the full analysis and reports what it *would* do, without placing
   orders. Read those sessions. If the reasoning is bad, you want to find out
   for free.
2. **Read the journal daily** for the first month. The journal is the only
   artifact that tells you whether the thesis quality is real or whether it is
   generating plausible-sounding narratives after the fact.
3. **Set a funding rule in advance**, before results exist. Deciding how much to
   add *after* seeing a win is how the largest loss gets sized.

## The sample size problem

The plan is to add capital as results warrant. §10 of `CLAUDE.md` binds the
agent to report this every week, and it is worth internalizing directly:

At a few trades per week, **early results contain almost no information.** A
strategy with a genuine 55% edge is underwater after 20 trades about a third of
the time. A strategy with no edge at all shows a profit after 20 trades about
half the time. Both facts are consequences of variance, not of strategy quality.

Thirty closed trades is the rough floor for any inference, and even that is thin.
Scaling capital on five good days is scaling on noise — and noise is symmetric,
so it will eventually hand you five bad ones at the larger size.

## Structure

```
CLAUDE.md                 constitution — always loaded, binding
engine/
  risk_engine.py          ALL money math. Single source of truth. Tested.
  test_risk_engine.py     70 unit tests: sizing, tiers, PDT, drawdown, gates
  test_doc_consistency.py 39 tests asserting docs and engine agree
  run_all_tests.py        runs both — the agent runs this before its first order
playbooks/                strategy specs — read during a run
  P1_equity_momentum.md   T0+  the only live playbook; measured, no edge
                               (P2/P3/P4 retired to the retired-playbooks branch)
research/                 the search: backtests, ledger, findings
  fetch_bars.py           534-name universe, 15y daily bars
  backtest_p1.py          lookahead-free harness, costs in bps
  test_backtest.py        29 tests incl. the lookahead guard
  funnel.py               which gate eliminates what
  gate_study.py           pre-registered single-gate attribution
  TEST_LEDGER.md          every run, including failures — multiple-comparisons
  FINDINGS.md             what has actually been measured
.claude/commands/
  trade.md                /trade  — one session
  review.md               /review — weekly, read-only
state/
  HALT                    operator kill switch — only you clear this
  HALT_TODAY              daily drawdown halt — self-clears next session
  positions.json          drift detection vs broker
  marks.json              drawdown reference marks
  day_trades.json         PDT counter
journal/                  append-only trade log, one file per day
```

## What is and is not verified

**Verified:** the arithmetic. Position sizing, tier gating, exposure aggregation,
PDT counting, drawdown triggers, and liquidity gates are implemented in tested
code, and the documents have been audited for internal contradictions (18 found
and fixed, including four surfaced by a review pass).

**Not verified:** whether any of it makes money. None of the strategy parameters
— the RSI band, the 12% stop, the delta range, the 21-DTE exit, the 2:1 R:R floor
— have been backtested. They are conventional values from standard practice, and
conventional is not the same as validated. A system can be perfectly consistent
and still have no edge; consistency only guarantees it will lose money in the way
you specified rather than in some way you did not.

That is the next piece of work if you want it: a backtest harness over historical
bars to find out whether the P1 setup has any edge before real capital sizes into
it.

## Not investment advice

You are responsible for every trade this places.
