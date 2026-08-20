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

108 tests, no dependencies beyond stdlib Python.

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

Account value is **$50**, funded and live as of 2026-08-20. Current tier:
**T0**. Trading runs unattended via the cloud routine
`trading-agent-daily-session`, weekdays 9:35–15:35 ET, hourly. The local
Windows task and `run_trade.ps1` are **deliberately disabled** — two schedulers
on one account race on `state/*.json`; never re-enable one without disabling
the other.

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
  test_doc_consistency.py 38 tests asserting docs and engine agree
  run_all_tests.py        runs both — the agent runs this before its first order
playbooks/                strategy specs — read during a run
  P1_equity_momentum.md   T0+  fractional shares, the only T0-viable strategy
  P2_swing_options.md     T1+  long calls (bullish) / long puts (bearish), 30-60 DTE
  P3_wheel.md             T3+  cash-secured puts → covered calls
  P4_0dte.md              T4   intraday, locked under $25k
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
