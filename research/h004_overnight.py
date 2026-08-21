"""H004 — where does the return actually live: overnight, or intraday?

CAMPAIGN.md H4. This is a MEASUREMENT, not a strategy, and it cannot be
"promoted" — there is no entry rule to promote. Its value is that it constrains
every other hypothesis: if the entire equity risk premium is earned between the
close and the next open, then any strategy that buys at the open and sells at
the close is fighting a headwind no edge has to overcome, and vice versa.

Decomposition, per symbol per session:

    overnight = open[i]  / close[i-1] - 1      (close to next open)
    intraday  = close[i] / open[i]    - 1      (open to close)
    (1 + overnight)(1 + intraday) = close[i]/close[i-1] = the full session

No lookahead is possible here — this measures realised returns, it makes no
decisions. Costs are not applied for the same reason: these are the returns of
holding, not of trading. A strategy built on either leg would pay costs; this
tells you whether it would be worth paying them.

    py research/h004_overnight.py
"""
from __future__ import annotations

import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import DATA_DIR, BENCHMARK, load_bars  # noqa: E402

TRAIN = ("2011-01-01", "2020-12-31")
RESERVE_NOTE = "1995-2010 is reserve and is deliberately not measured here."


def collect(window: tuple[str, str]) -> dict:
    overnight: list[float] = []
    intraday: list[float] = []
    per_symbol: dict[str, tuple[float, float]] = {}
    bench_on = bench_in = None

    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if len(s) < 400:
            continue
        on_sum = in_sum = 0.0
        n = 0
        for i in range(1, len(s)):
            if not (window[0] <= s.date[i] <= window[1]):
                continue
            if s.c[i - 1] <= 0 or s.o[i] <= 0:
                continue
            on = s.o[i] / s.c[i - 1] - 1.0
            it = s.c[i] / s.o[i] - 1.0
            # Guard against split/data artifacts: a 50%+ overnight move in a
            # mega-cap is far more likely bad data than a real gap, and a
            # handful of them would dominate an arithmetic mean.
            if abs(on) > 0.5 or abs(it) > 0.5:
                continue
            on_sum += on
            in_sum += it
            n += 1
            if s.symbol != BENCHMARK:
                overnight.append(on)
                intraday.append(it)
        if n:
            if s.symbol == BENCHMARK:
                bench_on, bench_in = on_sum, in_sum
            else:
                per_symbol[s.symbol] = (on_sum, in_sum)

    return {"overnight": overnight, "intraday": intraday,
            "per_symbol": per_symbol, "bench": (bench_on, bench_in)}


def describe(name: str, xs: list[float]) -> None:
    n = len(xs)
    if n < 2:
        print(f"  {name}: too few observations")
        return
    mean = statistics.fmean(xs)
    sd = statistics.stdev(xs)
    t = mean / (sd / math.sqrt(n))
    print(f"  {name:<10} mean {mean*10_000:+7.2f} bps/session   "
          f"sd {sd*100:5.2f}%   t {t:+7.2f}   n {n:,}")


def main() -> None:
    if not glob.glob(os.path.join(DATA_DIR, "*.csv")):
        print("No data. Run: py research/fetch_bars.py", file=sys.stderr)
        raise SystemExit(1)

    d = collect(TRAIN)
    print(f"H004 — overnight vs intraday decomposition   {TRAIN[0]} .. {TRAIN[1]}")
    print(f"  {RESERVE_NOTE}\n")

    describe("overnight", d["overnight"])
    describe("intraday", d["intraday"])

    on_tot = sum(d["overnight"])
    in_tot = sum(d["intraday"])
    print(f"\n  summed log-ish total across all name-sessions:")
    print(f"    overnight {on_tot*100:+9.1f}%      intraday {in_tot*100:+9.1f}%")

    # How consistent is the split across names? A premium that only shows up in
    # aggregate but flips sign in half the names is not a premium.
    both = [(sym, on, it) for sym, (on, it) in d["per_symbol"].items()]
    on_wins = sum(1 for _, on, it in both if on > it)
    print(f"\n  names where overnight beat intraday: {on_wins}/{len(both)} "
          f"({on_wins/max(len(both),1)*100:.0f}%)")

    bo, bi = d["bench"]
    if bo is not None:
        print(f"  {BENCHMARK}: overnight {bo*100:+.1f}%   intraday {bi*100:+.1f}%")

    print("\n  READING THIS: a large positive overnight leg with a flat or")
    print("  negative intraday leg means holding across the close is where the")
    print("  return is, and that any same-day strategy (CAMPAIGN H6 gap fade)")
    print("  starts from behind. It does NOT by itself constitute a tradeable")
    print("  edge: capturing it requires paying the spread every session, which")
    print("  at 10bps round trip is far larger than the per-session numbers above.")


if __name__ == "__main__":
    main()
