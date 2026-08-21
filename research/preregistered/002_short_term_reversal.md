# Hypothesis 002 — short-term reversal (the P5 vehicle)

**Status:** pre-registered 2026-08-22. Not yet run. Committed before
`research/backtest_mr.py` was written.

**Supersedes H001.** H001 tested the same family but specified a 2.5×ATR stop.
The operating mandate is explicit that a tight stop "converts the strategy's
core edge into its main loss source" for mean reversion, so H001's rules are
withdrawn rather than amended — a changed stop is a different hypothesis, and
editing it in place would let a rejected specification quietly become the
tested one. H001 is recorded in the ledger as withdrawn, unrun.

---

## Mechanism

Short-horizon selloffs in otherwise-healthy names are driven by sellers acting
under constraint rather than opinion: stop-outs, margin calls, risk-limit
deleveraging, fund redemptions. Their supply must clear by a deadline that is
not price-contingent. The other side is a liquidity provider who requires
compensation to absorb unwanted inventory, and that compensation is the return
being harvested. This is the short-term reversal effect, among the most
replicated in equities.

It is the **opposite** trade to P1, which bought strength and needed a trend to
continue. This buys weakness and needs only urgency to subside. Deliberate, not
a contradiction.

**Why it might fail:** the same price action is produced by news that
permanently repriced the company, and daily bars cannot tell the two apart. The
200-SMA filter is the only defence and it is weak. If genuine repricings
dominate the losers, the winners will not pay for them.

## Exact rules — no free parameters

```
Universe:  US common stock, price >= $5, 20d avg dollar volume >= $10M
           exclude leveraged/inverse ETFs, IPOs < 6 months
Filter:    close > 200-day SMA          (buy dips only inside uptrends)
Entry:     RSI(2) < 5  ->  enter at the NEXT OPEN (not a limit)
Exit:      close > 5-day SMA  ->  exit at the NEXT OPEN
Time stop: 10 sessions held -> exit regardless
Disaster:  -15% from entry -> exit
Sizing:    equal weight across MAX_CONCURRENT slots
```

**[HARD] No tight stop.** The time stop and the −15% disaster stop are the risk
controls and they are deliberate. P1's `min(swing low, entry − 2×ATR)` logic
must not be copied here; it is the one place that pattern is actively wrong.

**[HARD]** `RSI(2) < 5` and `close > SMA(200)` are fixed now. Trying 3/5/10/15
and reporting the best is fitting. One pre-registration, one number, one ledger
row.

## Definitions the mandate leaves open, fixed here before running

* **1R = 0.15 × entry price** — the disaster stop is the only bounded loss in
  the specification, so it defines the risk unit. Under this definition the
  promotion bar of avg R ≥ +0.05 means **≥ +0.75% average return per trade
  after costs**. Stating it now matters because choosing the R definition after
  seeing results would let the bar be met by redefinition.
* **Disaster stop is an intraday touch** (`low <= entry × 0.85`), filled at that
  level, or at the open when price gaps through it. Conservative: it books the
  loss on the day it happens rather than waiting for a close.
* **Exit fills at the open** following the signal, per the spec. The signal is
  computed on a close; nothing uses same-bar future information.
* **IPO < 6 months** is satisfied structurally: SMA(200) requires 200 prior
  bars, so nothing younger can ever produce a signal.
* **Leveraged/inverse ETFs** are absent from the universe by construction — it
  contains common stock only.
* **Costs:** 10bps round trip, charged once per position.

## Success criteria — all required, TRAIN only

* avg R ≥ **+0.05** after costs
* t ≥ **2.5**
* ≥ **500** trades

Higher t and trade count than the P1 protocol because frequency makes both
cheap here.

## Kill criterion

If TRAIN fails any of the three, this specification is dead. One ledger row, no
parameter search. The mandate allows exactly **one** alternative afterwards —
`RSI(2) < 10` with a 3-day maximum hold — which gets its own fresh
pre-registration and its own ledger row. If that also fails: "short-term
reversal shows no accessible edge after costs", and stop.

## Split

* **TRAIN** = signals 2011-01-01 … 2020-12-31
* **HOLDOUT** = 2021-01-01 … 2026-08-21 — one run, only if TRAIN clears
* **RESERVE** = 1995-01-01 … 2010-12-31 — untouched by any test in this
  project; not consulted for this hypothesis

## Gate check

`funnel.py`-style survivor counts are reported alongside the result. **[HARD]**
Any gate that zeroes out is the finding — report it and stop. That failure mode
already cost this project three days when two of P1's [HARD] rules turned out
to be mutually unsatisfiable.

**Tests used so far (TEST_LEDGER.md):** 20 train runs, 1 holdout use, all on
P1, now closed.
