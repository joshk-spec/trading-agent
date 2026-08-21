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
HOLDOUT = ("2021-01-01", "2026-12-31")

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


def simulate(s: Series, idx: int, cost_bps: float) -> MRTrade | None:
    """Enter at bar idx+1's open. Manage forward per the specification."""
    e = idx + 1
    if e >= len(s):
        return None
    entry = s.o[e]
    if entry <= 0:
        return None

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
            t.bars_held = max(held, 1)
            break

        # Reversion achieved: close back above the 5-day mean.
        x = exit_sma[d]
        if x is not None and s.c[d] > x:
            pending = "reverted"
        elif held >= MAX_HOLD_SESSIONS:
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


def run(window: tuple[str, str], cost_bps: float) -> tuple[list[MRTrade], list[int]]:
    trades: list[MRTrade] = []
    totals = [0] * len(GATES)
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < TREND_SMA + 50:
            continue
        idxs, counts = signals_and_funnel(s, window)
        totals = [a + b for a, b in zip(totals, counts)]
        busy_until = -1
        for i in idxs:
            # One position per symbol at a time, matching live behaviour.
            if i <= busy_until:
                continue
            tr = simulate(s, i, cost_bps)
            if tr is None:
                continue
            trades.append(tr)
            busy_until = i + tr.bars_held + 1
    return trades, totals


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

    rs = [t.r_multiple for t in trades]
    pcts = [t.pct_return for t in trades]
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
    print(f"  t-statistic:   {tstat:+.2f}")

    reasons: dict[str, list[float]] = {}
    for t in trades:
        reasons.setdefault(t.exit_reason, []).append(t.r_multiple)
    print("  exits:")
    for reason, vals in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        print(f"    {reason:<12} {len(vals):>6}  ({len(vals)/n*100:4.1f}%)  "
              f"avg {statistics.fmean(vals):+.4f}R")
    return avg, tstat, n


def main() -> int:
    p = argparse.ArgumentParser(description="Short-term reversal backtest (P5).")
    p.add_argument("--holdout", action="store_true",
                   help="ALSO run the holdout. Spends one of three total uses.")
    p.add_argument("--funnel", action="store_true", help="show gate survivor counts")
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    a = p.parse_args()

    if not glob.glob(os.path.join(DATA_DIR, "*.csv")):
        print("No data. Run: py research/fetch_bars.py", file=sys.stderr)
        return 1

    trades, totals = run(TRAIN, a.cost_bps)
    avg, tstat, n = report("TRAIN", TRAIN, trades, totals, a.cost_bps, True)

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
        ht, htot = run(HOLDOUT, a.cost_bps)
        report("HOLDOUT", HOLDOUT, ht, htot, a.cost_bps, False)
        print("\n  *** A HOLDOUT USE HAS BEEN SPENT — record it in TEST_LEDGER.md ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
