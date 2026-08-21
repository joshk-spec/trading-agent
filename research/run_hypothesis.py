"""Run one pre-registered hypothesis over the universe.

    py research/run_hypothesis.py H001                 # TRAIN only (default)
    py research/run_hypothesis.py H001 --holdout       # spends a holdout use

TRAIN is the only set consulted by default, and that is enforced rather than
suggested: --holdout must be passed explicitly, and the run prints a reminder
that the budget in TEST_LEDGER.md must be decremented by hand. Three holdout
consultations exist for the whole project; after that the period is burned and
no out-of-sample claim can be made from it again.
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    DATA_DIR, BENCHMARK, Indicators, Trade, load_bars, simulate, DEFAULT_COST_BPS,
)
from strategies import ALL  # noqa: E402

# Windows per CAMPAIGN.md. RESERVE (1995-2010) is deliberately absent: the
# deeper dataset made it available, no test in this project has touched it,
# and it stays that way until a hypothesis earns it.
TRAIN = ("2011-01-01", "2020-12-31")
HOLDOUT = ("2021-01-01", "2026-12-31")
RESERVE = ("1995-01-01", "2010-12-31")   # not wired to any flag, by design

# Promotion bar, from the mandate. All three required, on TRAIN.
BAR_AVG_R = 0.10
BAR_T = 2.0
BAR_TRADES = 100


def run(strategy, window, cost_bps: float) -> tuple[list[Trade], int]:
    trades: list[Trade] = []
    n_signals = 0
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < 400:
            continue
        ind = Indicators(s, ema_exit_period=strategy.ema_exit_period,
                         sma_exit_period=strategy.sma_exit_period)
        busy_until = -1
        for sig in strategy.signals(s, ind):
            if not (window[0] <= sig.date <= window[1]):
                continue
            n_signals += 1
            # One position per symbol at a time, matching live behaviour.
            if sig.idx <= busy_until:
                continue
            t = simulate(s, ind, sig, strategy.exits.stop_model,
                         cost_bps=cost_bps, exits=strategy.exits)
            if t is None:
                continue
            trades.append(t)
            busy_until = sig.idx + t.bars_held
    return trades, n_signals


def summarize(name: str, label: str, trades: list[Trade], n_signals: int,
              window, cost_bps: float) -> tuple[float, float, int]:
    n = len(trades)
    print(f"\n{name} — {label}   {window[0]} .. {window[1]}   cost {cost_bps:.0f}bps")
    print(f"  signals in window: {n_signals}")
    print(f"  trades taken:      {n}")
    if n < 2:
        print("  too few trades to evaluate")
        return 0.0, 0.0, n

    rs = [t.r_multiple for t in trades]
    avg = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    t_stat = avg / (sd / math.sqrt(n)) if sd else 0.0
    wins = [r for r in rs if r > 0]

    peak = cum = mdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)

    print(f"  win rate:      {len(wins)/n*100:5.1f}%")
    print(f"  average R:     {avg:+.3f}R")
    print(f"  total:         {sum(rs):+.1f}R")
    if wins:
        print(f"  avg win:       {statistics.fmean(wins):+.3f}R")
    losses = [r for r in rs if r <= 0]
    if losses:
        print(f"  avg loss:      {statistics.fmean(losses):+.3f}R")
    print(f"  max drawdown:  {mdd:.1f}R")
    print(f"  avg hold:      {statistics.fmean([t.bars_held for t in trades]):.1f} sessions")
    print(f"  std dev:       {sd:.3f}R")
    print(f"  t-statistic:   {t_stat:+.2f}")

    reasons: dict[str, list[float]] = {}
    for t in trades:
        reasons.setdefault(t.exit_reason, []).append(t.r_multiple)
    print("  exits:")
    for reason, vals in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        print(f"    {reason:<12} {len(vals):>5}  ({len(vals)/n*100:4.1f}%)  "
              f"avg {statistics.fmean(vals):+.3f}R")
    return avg, t_stat, n


def main() -> int:
    p = argparse.ArgumentParser(description="Run a pre-registered hypothesis.")
    p.add_argument("hypothesis", choices=sorted(ALL))
    p.add_argument("--holdout", action="store_true",
                   help="ALSO run the holdout. Spends one of three total uses.")
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    a = p.parse_args()

    strategy = ALL[a.hypothesis]
    prereg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "preregistered")
    match = [f for f in os.listdir(prereg) if f.startswith(a.hypothesis[1:].lstrip("0") or "0")
             or f.startswith(a.hypothesis[1:])]
    if not match:
        print(f"REFUSING: no pre-registration found for {a.hypothesis} in {prereg}.\n"
              f"A hypothesis written after seeing results is not a hypothesis.",
              file=sys.stderr)
        return 1
    print(f"pre-registration: {match[0]}")

    trades, sigs = run(strategy, TRAIN, a.cost_bps)
    avg, t_stat, n = summarize(f"{strategy.hypothesis_id} — {strategy.name}",
                               "TRAIN", trades, sigs, TRAIN, a.cost_bps)

    print("\n  promotion bar (all three required, on TRAIN):")
    checks = [
        (f"avg R >= +{BAR_AVG_R:.2f}", avg >= BAR_AVG_R, f"{avg:+.3f}R"),
        (f"t >= {BAR_T:.1f}", t_stat >= BAR_T, f"{t_stat:+.2f}"),
        (f"trades >= {BAR_TRADES}", n >= BAR_TRADES, str(n)),
    ]
    for label, ok, got in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}] {label:<18} got {got}")
    passed = all(ok for _, ok, _ in checks)
    print(f"\n  VERDICT: {'clears TRAIN — holdout is warranted' if passed else 'does not clear TRAIN'}")
    if not passed:
        print("  Kill criterion applies: record one line in TEST_LEDGER.md and stop.")
        print("  Do NOT search parameters to rescue it — that is how a measurement")
        print("  becomes a story.")

    if a.holdout:
        if not passed:
            print("\n  REFUSING --holdout: TRAIN did not clear the bar. Spending a")
            print("  holdout use on a failed hypothesis burns a scarce resource for")
            print("  no information.")
            return 0
        ht, hs = run(strategy, HOLDOUT, a.cost_bps)
        summarize(f"{strategy.hypothesis_id} — {strategy.name}",
                  "HOLDOUT", ht, hs, HOLDOUT, a.cost_bps)
        print("\n  *** A HOLDOUT USE HAS BEEN SPENT. Decrement the budget in")
        print("      research/TEST_LEDGER.md and record the result, pass or fail. ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
