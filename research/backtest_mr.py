"""Backtest of the short-term reversal specification (P5 vehicle).

Pre-registration: research/preregistered/002_short_term_reversal.md — read it
before changing anything here. Every parameter below is fixed by that document.

WHY A SEPARATE SIMULATOR. backtest_p1.py's exit engine trails stops, trims at
+2R and voids on gaps — none of which this specification has, and two of which
it explicitly forbids. Bending that engine into this shape would have meant
adding flags whose only purpose is to switch off most of it, and the mandate's
one [HARD] warning here is that P1's stop logic must not be copied. This
simulator is deliberately small enough to read in one sitting:

    enter at the next open, exit at the next open after a signal, or on an
    intraday touch of the -15% disaster level, or after 10 sessions.

The causal indicators, the cost model and the lookahead discipline ARE reused
from backtest_p1 — that harness is tested and its guarantees are the reason its
numbers can be trusted.

    py research/backtest_mr.py                 # TRAIN
    py research/backtest_mr.py --funnel        # gate survivor counts
    py research/backtest_mr.py --holdout       # spends one of three holdout uses
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    DATA_DIR, BENCHMARK, Series, load_bars, sma, rsi, DEFAULT_COST_BPS,
)

# ---- Specification constants (pre-registration 002). Do not tune. ----
MIN_PRICE          = 5.00
MIN_ADV_DOLLARS    = 10_000_000
TREND_SMA          = 200
RSI_PERIOD         = 2
RSI_THRESHOLD      = 5.0
EXIT_SMA           = 5
MAX_HOLD_SESSIONS  = 10
DISASTER_STOP_PCT  = 0.15          # 1R is defined as this fraction of entry
ADV_LOOKBACK       = 20

TRAIN = ("2011-01-01", "2020-12-31")
# End date is the pre-registration's, not "end of data": once fetch_bars.py
# runs again the window would silently widen, which is exactly the drift a
# one-shot holdout protocol exists to prevent.
HOLDOUT = ("2021-01-01", "2026-08-21")

# Promotion bar (pre-registration 002). All three required, TRAIN only.
BAR_AVG_R, BAR_T, BAR_TRADES = 0.05, 2.5, 500

GATES = ["bars evaluated", "price >= $5", "ADV >= $10M",
         "close > SMA(200)", "RSI(2) < 5", "next bar exists (enterable)"]


@dataclass
class MRTrade:
    symbol: str
    signal_date: str
    entry_date: str
    entry: float
    exit_date: str = ""
    exit_price: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""
    r_multiple: float = 0.0
    pct_return: float = 0.0
    rsi_at_signal: float = 0.0


def signals_and_funnel(s: Series, window: tuple[str, str]) -> tuple[list[int], list[int]]:
    """Indices of signal bars, plus per-gate survivor counts.

    Causal by construction: bar i uses only closes up to i. Entry happens at
    i+1 and is handled by the caller, which may look at bar i+1's OPEN only."""
    closes, vols = s.c, s.v
    trend = sma(closes, TREND_SMA)
    fast = rsi(closes, RSI_PERIOD)
    dollar = [closes[k] * vols[k] for k in range(len(s))]
    adv = sma(dollar, ADV_LOOKBACK)

    counts = [0] * len(GATES)
    out: list[int] = []
    for i in range(TREND_SMA + 2, len(s)):
        if not (window[0] <= s.date[i] <= window[1]):
            continue
        k = 0
        counts[k] += 1; k += 1
        if closes[i] < MIN_PRICE:
            continue
        counts[k] += 1; k += 1
        if adv[i] is None or adv[i] < MIN_ADV_DOLLARS:
            continue
        counts[k] += 1; k += 1
        t = trend[i]
        if t is None or closes[i] <= t:
            continue
        counts[k] += 1; k += 1
        r = fast[i]
        if r is None or r >= RSI_THRESHOLD:
            continue
        counts[k] += 1; k += 1
        if i + 1 >= len(s):
            continue                      # cannot enter; not a signal
        counts[k] += 1
        out.append(i)
    return out, counts


def simulate(s: Series, idx: int, cost_bps: float,
             exit_sma: list[float | None] | None = None) -> MRTrade | None:
    """Enter at bar idx+1's open. Manage forward per the specification.

    `exit_sma` is passed in by run() because it is a pure function of the
    series: recomputing a 5-bar mean over ~4,000 bars inside each of 16,000
    simulate() calls was pointless O(bars) work per trade."""
    e = idx + 1
    if e >= len(s):
        return None
    entry = s.o[e]
    if entry <= 0:
        return None

    if exit_sma is None:
        exit_sma = sma(s.c, EXIT_SMA)
    disaster = entry * (1.0 - DISASTER_STOP_PCT)
    R = entry * DISASTER_STOP_PCT          # 1R, per the pre-registration

    t = MRTrade(s.symbol, s.date[idx], s.date[e], entry)
    pending = ""                            # decided on a close, filled next open

    d = e
    while d < len(s):
        held = d - e

        # A close-based exit decided yesterday fills at today's open.
        if pending:
            t.exit_price, t.exit_date, t.exit_reason = s.o[d], s.date[d], pending
            t.bars_held = held
            break

        # Disaster stop: intraday touch, filled at the level, or at the open if
        # price gapped straight through it. Checked first — within one bar we
        # cannot know the order, so we take the unfavourable reading.
        if s.l[d] <= disaster:
            t.exit_price = min(s.o[d], disaster)
            t.exit_date, t.exit_reason = s.date[d], "disaster"
            t.bars_held = held        # 0 when the entry bar itself gapped through
            break

        # Reversion achieved: close back above the 5-day mean.
        x = exit_sma[d]
        if x is not None and s.c[d] > x:
            pending = "reverted"
        elif held >= MAX_HOLD_SESSIONS - 1:
            # Decided on this close, filled at the next open, so the position
            # is exited ON session MAX_HOLD_SESSIONS. Setting it at
            # `held >= MAX_HOLD_SESSIONS` held for 11 sessions, one more than
            # the pre-registration allows.
            pending = "time_stop"

        d += 1

    if not t.exit_reason:                   # ran out of data
        t.exit_price, t.exit_date = s.c[-1], s.date[-1]
        t.exit_reason, t.bars_held = "end_of_data", len(s) - 1 - e

    gross = (t.exit_price - entry) / entry
    cost = cost_bps / 10_000.0              # one round trip, per position
    t.pct_return = gross - cost
    t.r_multiple = t.pct_return * entry / R  # == pct_return / DISASTER_STOP_PCT
    return t


def candidates(window: tuple[str, str], cost_bps: float
               ) -> tuple[list[MRTrade], list[int]]:
    """Every trade the rules would generate if capital were unlimited.

    A trade's outcome does not depend on what else is open, so generating all
    candidates first and applying the portfolio constraint afterwards is exact,
    not an approximation."""
    out: list[MRTrade] = []
    totals = [0] * len(GATES)
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < TREND_SMA + 50:
            continue
        sig, counts = signals_and_funnel(s, window)
        totals = [a + b for a, b in zip(totals, counts)]
        exit_sma = sma(s.c, EXIT_SMA)
        fast = rsi(s.c, RSI_PERIOD)
        busy_until = -1
        for i in sig:
            # One position per symbol at a time. Entry is i+1 and the exit bar
            # is i+1+bars_held, so a later signal at j >= i+bars_held+1 enters
            # strictly after this one closed. The previous `+1` here was one bar
            # more conservative than that and silently dropped valid signals.
            if i < busy_until:
                continue
            tr = simulate(s, i, cost_bps, exit_sma)
            if tr is None:
                continue
            tr.rsi_at_signal = fast[i] if fast[i] is not None else 0.0
            out.append(tr)
            busy_until = i + tr.bars_held + 1
    return out, totals


def allocate(cands: list[MRTrade], max_slots: int,
             tiebreak: str = "rsi") -> tuple[list[MRTrade], dict]:
    """Apply the portfolio constraint: at most `max_slots` positions at once.

    WHY THIS EXISTS. Without it the backtest books every signal, and on TRAIN
    that means a median of 17 and a peak of 228 simultaneous positions — 52% of
    days exceed even 15 slots. Those trades are not executable, so an average
    taken over them describes a portfolio nobody could run.

    Allocation walks forward in date order, frees slots whose exit date has
    passed, then fills from that day's candidates. When more signals arrive than
    slots remain, `tiebreak` decides:
      "rsi"   — most oversold first, following the mechanism being tested
      "random"— seeded, for checking the choice is not load-bearing
      "symbol"— alphabetical, a deliberately arbitrary control
    The rule IS a free parameter, so all three are reported rather than the
    best one being quoted."""
    by_day: dict[str, list[MRTrade]] = {}
    for t in cands:
        by_day.setdefault(t.entry_date, []).append(t)

    rnd = random.Random(20260822)
    taken: list[MRTrade] = []
    open_until: list[str] = []          # exit dates of currently-held positions
    skipped = 0

    for day in sorted(by_day):
        open_until = [d for d in open_until if d > day]
        todays = by_day[day]
        if tiebreak == "rsi":
            todays = sorted(todays, key=lambda t: t.rsi_at_signal)
        elif tiebreak == "symbol":
            todays = sorted(todays, key=lambda t: t.symbol)
        else:
            todays = list(todays)
            rnd.shuffle(todays)

        for t in todays:
            if len(open_until) >= max_slots:
                skipped += 1
                continue
            taken.append(t)
            open_until.append(t.exit_date)

    return taken, {"candidates": len(cands), "taken": len(taken),
                   "skipped": skipped, "slots": max_slots, "tiebreak": tiebreak}


def run(window: tuple[str, str], cost_bps: float, max_slots: int = 0,
        tiebreak: str = "rsi") -> tuple[list[MRTrade], list[int]]:
    """max_slots=0 means unconstrained (the old, non-executable behaviour)."""
    cands, totals = candidates(window, cost_bps)
    if not max_slots:
        return cands, totals
    taken, _ = allocate(cands, max_slots, tiebreak)
    return taken, totals


def clustered_t(trades: list[MRTrade]) -> tuple[float, int]:
    """t-statistic treating each entry DAY as one observation.

    Signals fire together on market-wide selloffs -- median 5 a day, peak 110 --
    so a per-trade t counts one bet many times over. On TRAIN this inflates the
    statistic roughly 2.9x (+9.91 naive vs +3.47 clustered). The promotion gate
    reads THIS number: deciding a scarce holdout spend on the naive one would
    mean spending it on an artifact."""
    by_day: dict[str, list[float]] = {}
    for t in trades:
        by_day.setdefault(t.entry_date, []).append(t.r_multiple)
    if len(by_day) < 2:
        return 0.0, len(by_day)
    day_avgs = [statistics.fmean(v) for v in by_day.values()]
    sd = statistics.stdev(day_avgs)
    if sd == 0:
        return 0.0, len(day_avgs)
    return statistics.fmean(day_avgs) / (sd / math.sqrt(len(day_avgs))), len(day_avgs)


def report(label: str, window, trades: list[MRTrade], totals: list[int],
           cost_bps: float, show_funnel: bool) -> tuple[float, float, int]:
    print(f"\nSHORT-TERM REVERSAL — {label}   {window[0]} .. {window[1]}   "
          f"cost {cost_bps:.0f}bps")
    if show_funnel:
        print("\n  gate survivors:")
        prev = None
        for name, n in zip(GATES, totals):
            pct = f"  ({n/prev*100:5.1f}% of prev)" if prev else ""
            print(f"    {name:<28} {n:>10,}{pct}")
            prev = n
        if totals[-1] == 0:
            print("\n  *** A GATE ZEROED OUT — that is the finding. Stop here. ***")

    n = len(trades)
    print(f"\n  trades: {n:,}")
    if n < 2:
        print("  too few trades to evaluate")
        return 0.0, 0.0, n

    # Chronological by exit date. Walking the list as emitted meant walking
    # AAPL's entire history, then AA's -- a symbol-ordered sequence, not an
    # equity curve. That understated max drawdown by ~8.6x.
    chrono = sorted(trades, key=lambda t: (t.exit_date, t.symbol))
    rs = [t.r_multiple for t in chrono]
    pcts = [t.pct_return for t in chrono]
    avg = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    tstat = avg / (sd / math.sqrt(n)) if sd else 0.0
    wins = [r for r in rs if r > 0]

    peak = cum = mdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)

    print(f"  win rate:      {len(wins)/n*100:5.1f}%")
    print(f"  average R:     {avg:+.4f}R   (1R = {DISASTER_STOP_PCT:.0%} of entry)")
    print(f"  avg % return:  {statistics.fmean(pcts)*100:+.3f}% per trade, after costs")
    print(f"  total:         {sum(rs):+.1f}R")
    if wins:
        print(f"  avg win:       {statistics.fmean(wins):+.4f}R")
    losses = [r for r in rs if r <= 0]
    if losses:
        print(f"  avg loss:      {statistics.fmean(losses):+.4f}R")
    print(f"  max drawdown:  {mdd:.1f}R")
    print(f"  avg hold:      {statistics.fmean([t.bars_held for t in trades]):.1f} sessions")
    print(f"  std dev:       {sd:.4f}R")
    print(f"  t-statistic:   {tstat:+.2f}   (naive; assumes trades are independent)")
    cl_t, cl_n = clustered_t(trades)
    print(f"  clustered t:   {cl_t:+.2f}   ({cl_n:,} distinct entry days) <- the one that counts")

    reasons: dict[str, list[float]] = {}
    for t in trades:
        reasons.setdefault(t.exit_reason, []).append(t.r_multiple)
    print("  exits:")
    for reason, vals in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        print(f"    {reason:<12} {len(vals):>6}  ({len(vals)/n*100:4.1f}%)  "
              f"avg {statistics.fmean(vals):+.4f}R")
    return avg, cl_t, n


def main() -> int:
    p = argparse.ArgumentParser(description="Short-term reversal backtest (P5).")
    p.add_argument("--holdout", action="store_true",
                   help="ALSO run the holdout. Spends one of three total uses.")
    p.add_argument("--funnel", action="store_true", help="show gate survivor counts")
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    p.add_argument("--slots", type=int, default=15,
                   help="MAX_CONCURRENT portfolio slots; 0 = unconstrained "
                        "(not executable, for comparison only)")
    p.add_argument("--tiebreak", choices=["rsi", "random", "symbol"], default="rsi")
    a = p.parse_args()

    if not glob.glob(os.path.join(DATA_DIR, "*.csv")):
        print("No data. Run: py research/fetch_bars.py", file=sys.stderr)
        return 1

    trades, totals = run(TRAIN, a.cost_bps, a.slots, a.tiebreak)
    avg, tstat, n = report(f"TRAIN [{a.slots or 'unconstrained'} slots,"
                           f" {a.tiebreak}]", TRAIN, trades, totals,
                           a.cost_bps, True)

    print("\n  promotion bar (all three required, TRAIN):")
    checks = [(f"avg R >= +{BAR_AVG_R}", avg >= BAR_AVG_R, f"{avg:+.4f}R"),
              (f"t >= {BAR_T}", tstat >= BAR_T, f"{tstat:+.2f}"),
              (f"trades >= {BAR_TRADES}", n >= BAR_TRADES, f"{n:,}")]
    for label, ok, got in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}] {label:<18} got {got}")
    passed = all(ok for _, ok, _ in checks)
    print(f"\n  VERDICT: {'clears TRAIN — holdout warranted' if passed else 'does not clear TRAIN'}")

    if a.holdout:
        if not passed:
            print("\n  REFUSING --holdout: TRAIN did not clear the bar. Spending a")
            print("  scarce holdout use on a failed hypothesis buys no information.")
            return 0
        ht, htot = run(HOLDOUT, a.cost_bps, a.slots, a.tiebreak)
        report("HOLDOUT", HOLDOUT, ht, htot, a.cost_bps, False)
        print("\n  *** A HOLDOUT USE HAS BEEN SPENT — record it in TEST_LEDGER.md ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
