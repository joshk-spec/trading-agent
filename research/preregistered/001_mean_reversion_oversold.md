# Hypothesis 001 — mean reversion in liquid large caps after forced selling

**Status:** pre-registered 2026-08-22. Not yet run.

**Mechanism:** Some sellers must transact by a deadline regardless of price —
margin calls, risk-limit deleveraging, index-rebalance flows, tax-loss selling
into year end, and fund redemptions. Their supply arrives faster than natural
buyers appear, so a liquid name in an intact uptrend can trade several percent
below where it clears a day or two later. The other side of this trade is the
liquidity provider paid for absorbing that supply; the constraint that makes it
work is that the seller's deadline is not price-contingent.

This is a genuinely different mechanism from P1. P1 bought *strength* and
required the market to keep trending. This buys *weakness* and requires only
that the dislocation closes — a shorter, more specific claim.

**Why it might not work:** the same price action is produced by real news that
permanently repriced the company, and daily bars cannot distinguish the two. If
the losers are dominated by genuine repricings, the winners will not pay for
them. The 200-SMA filter is the only defence and it is a weak one.

**Universe:** the 534-name liquid US equity set in `fetch_bars.py`. Price ≥ $5,
20-day average dollar volume ≥ $50M. Survivorship-biased, so any positive
result is an optimistic bound.

**Exact rules:**
- **Setup:** `close > SMA(200)` — buy dips in uptrends only, never falling knives.
- **Trigger:** `RSI(2) < 5.0` on the signal bar. RSI(2), not RSI(14): the claim
  is about a 2–4 day dislocation, and a 14-day window cannot resolve one.
- **Confirmation:** at least 3 consecutive lower closes into the signal.
- **Entry:** next session, limit at or below the signal close (same fill model
  as P1). Gap rule inverted from P1 — a gap *down* is the setup improving, so
  gap-up above +2% voids, gap-down does not.
- **Stop:** `entry − 2.5 × ATR(14)`. Wider than P1's 2.0 because the entry is
  deliberately into falling price and a tight stop would be noise-triggered.
- **Target:** `SMA(20)` — the level the dislocation is expected to close back
  toward. This is a mean-reversion objective, not a structural resistance
  level, so **P1's 2.0 minimum reward:risk does not apply** and is disabled.
- **Exit:** whole position at target if touched; otherwise `close > SMA(5)`
  (reversion achieved); hard exit at 10 sessions.
- **No 20-EMA trend exit, no 2R trim, no breakeven trail** — those are
  trend-riding rules and this is not a trend trade.
- **Costs:** 10bps round trip.

**Parameters, fixed now, with reasons:**
| parameter | value | why this value |
|---|---|---|
| RSI period | 2 | matches the 2–4 day dislocation the mechanism claims |
| RSI threshold | 5.0 | conventional short-term-oversold level; not tuned |
| trend filter | SMA(200) | standard long-term regime line |
| down days | 3 | minimum that distinguishes a slide from one bad print |
| ATR stop multiple | 2.5 | wider than P1's 2.0 because entry is into weakness |
| target | SMA(20) | the mean being reverted to |
| max hold | 10 sessions | the claim is days, not weeks; expire if wrong |

No ranges. A range would be two hypotheses.

**Success criteria — all required, on TRAIN only:**
- avg R ≥ +0.10 after 10bps costs
- t ≥ 2.0, Bonferroni-adjusted by the ledger's running test count
- ≥ 100 trades

**Kill criterion:** if train avg R < 0 or trades < 100, this is dead and gets
one line in the ledger. No parameter search afterwards — that is how the 20-EMA
mistake nearly happened, and it is how 87 trades became an unfalsifiable story.

**Split:** TRAIN = signals 1995-01-01 … 2015-12-31. HOLDOUT = 2016-01-01 …
2026-08-21, consulted only if TRAIN passes, once.

**Tests used so far (from TEST_LEDGER.md):** 20 train tests, 1 holdout
consultation, all on P1, which is now closed.
