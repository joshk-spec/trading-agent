"""Why does every P1 candidate fail the 2.0 reward:risk gate?

The funnel shows 341 bar-days over 15 years clearing every P1 condition except
reward:risk, and ZERO clearing that one. Before concluding the rule set is
unsatisfiable, test whether that is an artifact of how "structural target" was
operationalised. P1 says the target must come from "real structure — prior
high, measured move, or a resistance level" without picking one, so this
measures the reward:risk each admissible reading produces on the same 341
candidates.

    py research/target_study.py
"""
from __future__ import annotations

import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    DATA_DIR, BENCHMARK, Indicators, load_bars,
    MIN_PRICE, MIN_ADV_DOLLARS, SMA_SLOW, SMA_SLOPE_LOOKBACK,
    HIGH_52W_LOOKBACK, MAX_PCT_BELOW_HIGH, SWING_LOOKBACK,
    RETRACE_MIN, RETRACE_MAX, EMA_PROXIMITY, RSI_BAND_LO, RSI_BAND_HI,
    RSI_FLOOR, RSI_WINDOW, VOL_AVG_LOOKBACK, ATR_STOP_MULT, MAX_STOP_PCT,
    MIN_RR, TARGET_LOOKBACK,
)


def collect() -> list[dict]:
    """Every bar-day passing all P1 gates EXCEPT reward:risk."""
    spy = load_bars(os.path.join(DATA_DIR, f"{BENCHMARK}.csv"))
    spy_ind = Indicators(spy)
    spy_idx = {d: i for i, d in enumerate(spy.date)}
    out: list[dict] = []

    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < 400:
            continue
        ind = Indicators(s)
        start = max(SMA_SLOW, HIGH_52W_LOOKBACK, TARGET_LOOKBACK) + 2

        for i in range(start, len(s) - 1):
            if s.c[i] < MIN_PRICE: continue
            if ind.adv[i] is None or ind.adv[i] < MIN_ADV_DOLLARS: continue
            j = spy_idx.get(s.date[i])
            if j is None: continue
            fb, slb = spy_ind.sma_fast[j], spy_ind.sma_slow[j]
            if fb is None or slb is None or spy.c[j] < slb or spy.c[j] <= fb: continue
            f, sl = ind.sma_fast[i], ind.sma_slow[i]
            if f is None or sl is None or not (s.c[i] > f > sl): continue
            pf = ind.sma_fast[i - SMA_SLOPE_LOOKBACK]
            if pf is None or f <= pf: continue
            high_252 = max(s.h[i - HIGH_52W_LOOKBACK + 1:i + 1])
            if high_252 <= 0 or (high_252 - s.c[i]) / high_252 > MAX_PCT_BELOW_HIGH: continue
            lo_w = i - SWING_LOOKBACK + 1
            swing_high = max(s.h[lo_w:i + 1])
            sh_idx = lo_w + s.h[lo_w:i + 1].index(swing_high)
            if sh_idx >= i: continue
            pull_low = min(s.l[sh_idx:i + 1])
            retr = (swing_high - pull_low) / swing_high
            if not (RETRACE_MIN <= retr <= RETRACE_MAX): continue
            e20 = ind.ema20[i]
            if e20 is None or pull_low > e20 * (1 + EMA_PROXIMITY): continue
            if sh_idx - VOL_AVG_LOOKBACK // 2 < 0: continue
            if statistics.fmean(s.v[sh_idx:i + 1]) >= statistics.fmean(s.v[sh_idx - 10:sh_idx]): continue
            win = [x for x in ind.rsi[i - RSI_WINDOW + 1:i + 1] if x is not None]
            if len(win) < RSI_WINDOW: continue
            tr = min(win)
            if not (RSI_BAND_LO <= tr <= RSI_BAND_HI) or tr < RSI_FLOOR: continue
            if ind.rsi[i] is None or ind.rsi[i-1] is None or ind.rsi[i] <= ind.rsi[i-1]: continue
            rs, rb = ind.roc20[i], spy_ind.roc20[j]
            if rs is None or rb is None or rs <= rb: continue
            if s.c[i] <= s.h[i - 1]: continue
            if ind.vol_avg[i] is None or s.v[i] < ind.vol_avg[i]: continue
            a = ind.atr[i]
            if a is None: continue
            stop = min(pull_low, s.c[i] - ATR_STOP_MULT * a)
            if stop <= 0 or stop >= s.c[i]: continue
            if (s.c[i] - stop) / s.c[i] > MAX_STOP_PCT: continue

            out.append({
                "symbol": s.symbol, "date": s.date[i], "entry": s.c[i], "stop": stop,
                "swing_high": swing_high, "pull_low": pull_low,
                "high_60": max(s.h[i - TARGET_LOOKBACK + 1:i + 1]),
                "high_252": high_252,
            })
    return out


def main() -> None:
    cands = collect()
    if not cands:
        print("no candidates")
        return

    print(f"candidates clearing every P1 gate except reward:risk: {len(cands)}\n")

    # The geometry, stated plainly.
    up_60 = [(c["high_60"] - c["entry"]) / c["entry"] * 100 for c in cands]
    up_252 = [(c["high_252"] - c["entry"]) / c["entry"] * 100 for c in cands]
    down = [(c["entry"] - c["stop"]) / c["entry"] * 100 for c in cands]
    print("  at the moment of entry, as % of entry price:")
    print(f"    room up to the 60-day high    median {statistics.median(up_60):5.2f}%")
    print(f"    room up to the 252-day high   median {statistics.median(up_252):5.2f}%")
    print(f"    room down to the stop         median {statistics.median(down):5.2f}%")
    print()

    def report(name: str, fn) -> None:
        rrs = []
        for c in cands:
            t = fn(c)
            r = c["entry"] - c["stop"]
            if t > c["entry"] and r > 0:
                rrs.append((t - c["entry"]) / r)
        if not rrs:
            print(f"  {name:<44} no valid targets")
            return
        rrs.sort()
        passed = sum(1 for x in rrs if x >= MIN_RR)
        print(f"  {name:<44} median {statistics.median(rrs):5.2f}  "
              f"max {max(rrs):5.2f}  pass>=2.0 {passed:>4} ({passed/len(cands)*100:4.1f}%)")

    print("  reward:risk under each admissible reading of 'structural target':")
    report("prior 60-day high", lambda c: c["high_60"])
    report("prior 252-day high (52-week)", lambda c: c["high_252"])
    report("swing high of this pullback", lambda c: c["swing_high"])
    # Measured move: project the pullback's depth up from the swing high.
    report("measured move (swing high + retrace depth)",
           lambda c: c["swing_high"] + (c["swing_high"] - c["pull_low"]))
    # Measured move x2 — an aggressive but still structural reading.
    report("measured move x2", lambda c: c["swing_high"] + 2 * (c["swing_high"] - c["pull_low"]))

    print()
    print("  what stop distance WOULD clear 2.0 against the 252-day high:")
    need = [(c["high_252"] - c["entry"]) / 2.0 / c["entry"] * 100 for c in cands
            if c["high_252"] > c["entry"]]
    if need:
        print(f"    required stop <= {statistics.median(need):.2f}% of entry (median), "
              f"vs the {statistics.median(down):.2f}% the structural stop actually gives")


if __name__ == "__main__":
    main()
