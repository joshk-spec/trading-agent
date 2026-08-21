"""Diagnostic: which P1 gate eliminates candidates, and how many survive each?

`backtest_p1.find_signals` returns only survivors, so a zero result is
ambiguous — it could be a genuinely unreachable rule set or a bug in one
condition. This replays the identical conditions in the identical order and
counts how many bar-days pass each successive gate, turning "zero" into a
specific answer about WHICH gate is responsible.

The conditions here are duplicated from find_signals deliberately: a shared
helper that both used could hide a bug in the shared part. `test_funnel.py`
asserts the two agree on the final count for every symbol, so the duplication
cannot silently drift.

    py research/funnel.py
"""
from __future__ import annotations

import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    DATA_DIR, BENCHMARK, Indicators, load_bars,
    MIN_PRICE, MIN_ADV_DOLLARS, SMA_FAST, SMA_SLOW, SMA_SLOPE_LOOKBACK,
    HIGH_52W_LOOKBACK, MAX_PCT_BELOW_HIGH, SWING_LOOKBACK,
    RETRACE_MIN, RETRACE_MAX, EMA_PROXIMITY, RSI_BAND_LO, RSI_BAND_HI,
    RSI_FLOOR, RSI_WINDOW, VOL_AVG_LOOKBACK, ATR_STOP_MULT, MAX_STOP_PCT,
    MIN_RR, TARGET_LOOKBACK, TIME_STOP_SESSIONS,
)

STAGES = [
    "bars evaluated",
    "price >= $5",
    "ADV >= $50M",
    "SPY regime ok",
    "close > SMA50 > SMA200",
    "SMA50 rising (10d)",
    "within 8% of 252d high",
    "swing high is in the past",
    "retracement 3-10%",
    "pullback reached 20-EMA",
    "pullback vol < impulse vol",
    "RSI trough in 40-55",
    "RSI turned up",
    "outperformed SPY (20d)",
    "close > prior high",
    "volume >= 20d avg",
    "stop <= 12% of entry",
    "structural target above entry",
    "reward:risk >= 2.0",
]


def run() -> list[int]:
    spy = load_bars(os.path.join(DATA_DIR, f"{BENCHMARK}.csv"))
    spy_ind = Indicators(spy)
    spy_idx = {d: i for i, d in enumerate(spy.date)}
    counts = [0] * len(STAGES)
    # Diagnostics for the two gates most likely to be the binding pair.
    rr_samples: list[float] = []
    stop_pct_samples: list[float] = []

    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < 400:
            continue
        ind = Indicators(s)
        start = max(SMA_SLOW, HIGH_52W_LOOKBACK, TARGET_LOOKBACK) + 2

        for i in range(start, len(s) - 1):
            k = 0
            counts[k] += 1; k += 1

            if s.c[i] < MIN_PRICE: continue
            counts[k] += 1; k += 1
            if ind.adv[i] is None or ind.adv[i] < MIN_ADV_DOLLARS: continue
            counts[k] += 1; k += 1

            j = spy_idx.get(s.date[i])
            if j is None: continue
            f_b, sl_b = spy_ind.sma_fast[j], spy_ind.sma_slow[j]
            if f_b is None or sl_b is None or spy.c[j] < sl_b or spy.c[j] <= f_b: continue
            counts[k] += 1; k += 1

            f, sl = ind.sma_fast[i], ind.sma_slow[i]
            if f is None or sl is None or not (s.c[i] > f > sl): continue
            counts[k] += 1; k += 1

            prev_f = ind.sma_fast[i - SMA_SLOPE_LOOKBACK]
            if prev_f is None or f <= prev_f: continue
            counts[k] += 1; k += 1

            high_252 = max(s.h[i - HIGH_52W_LOOKBACK + 1:i + 1])
            if high_252 <= 0 or (high_252 - s.c[i]) / high_252 > MAX_PCT_BELOW_HIGH: continue
            counts[k] += 1; k += 1

            lo_w = i - SWING_LOOKBACK + 1
            swing_high = max(s.h[lo_w:i + 1])
            sh_idx = lo_w + s.h[lo_w:i + 1].index(swing_high)
            if sh_idx >= i: continue
            counts[k] += 1; k += 1

            pull_low = min(s.l[sh_idx:i + 1])
            retrace = (swing_high - pull_low) / swing_high
            if not (RETRACE_MIN <= retrace <= RETRACE_MAX): continue
            counts[k] += 1; k += 1

            e20 = ind.ema20[i]
            if e20 is None or pull_low > e20 * (1 + EMA_PROXIMITY): continue
            counts[k] += 1; k += 1

            if sh_idx - VOL_AVG_LOOKBACK // 2 < 0: continue
            pull_vol = statistics.fmean(s.v[sh_idx:i + 1])
            impulse_vol = statistics.fmean(s.v[sh_idx - 10:sh_idx])
            if impulse_vol <= 0 or pull_vol >= impulse_vol: continue
            counts[k] += 1; k += 1

            window = [x for x in ind.rsi[i - RSI_WINDOW + 1:i + 1] if x is not None]
            if len(window) < RSI_WINDOW: continue
            trough = min(window)
            if not (RSI_BAND_LO <= trough <= RSI_BAND_HI) or trough < RSI_FLOOR: continue
            counts[k] += 1; k += 1

            if ind.rsi[i] is None or ind.rsi[i - 1] is None or ind.rsi[i] <= ind.rsi[i - 1]: continue
            counts[k] += 1; k += 1

            r_sym, r_spy = ind.roc20[i], spy_ind.roc20[j]
            if r_sym is None or r_spy is None or r_sym <= r_spy: continue
            counts[k] += 1; k += 1

            if s.c[i] <= s.h[i - 1]: continue
            counts[k] += 1; k += 1

            if ind.vol_avg[i] is None or s.v[i] < ind.vol_avg[i]: continue
            counts[k] += 1; k += 1

            a = ind.atr[i]
            if a is None: continue
            stop = min(pull_low, s.c[i] - ATR_STOP_MULT * a)
            if stop <= 0 or stop >= s.c[i]: continue
            stop_pct = (s.c[i] - stop) / s.c[i]
            stop_pct_samples.append(stop_pct)
            if stop_pct > MAX_STOP_PCT: continue
            counts[k] += 1; k += 1

            target = max(s.h[i - TARGET_LOOKBACK + 1:i + 1])
            if target <= s.c[i]: continue
            counts[k] += 1; k += 1

            rr = (target - s.c[i]) / (s.c[i] - stop)
            rr_samples.append(rr)
            if rr < MIN_RR: continue
            counts[k] += 1; k += 1

    print(f"{'stage':<34} {'survivors':>10}   {'% of prev':>9}")
    print("-" * 58)
    for name, n in zip(STAGES, counts):
        print(f"{name:<34} {n:>10,}", end="")
        print()
    print("-" * 58)
    prev = None
    for name, n in zip(STAGES, counts):
        if prev is not None and prev > 0:
            print(f"  {name:<32} kept {n/prev*100:5.1f}% of previous stage")
        prev = n

    if stop_pct_samples:
        print(f"\nstop distance at the trigger (n={len(stop_pct_samples):,}): "
              f"median {statistics.median(stop_pct_samples)*100:.1f}% of entry, "
              f"pass rate <=12%: "
              f"{sum(1 for x in stop_pct_samples if x <= MAX_STOP_PCT)/len(stop_pct_samples)*100:.1f}%")
    if rr_samples:
        rr_samples.sort()
        print(f"reward:risk to the 60d high (n={len(rr_samples):,}): "
              f"median {statistics.median(rr_samples):.2f}, "
              f"90th pct {rr_samples[int(len(rr_samples)*0.9)]:.2f}, "
              f"max {max(rr_samples):.2f}, "
              f"pass rate >=2.0: "
              f"{sum(1 for x in rr_samples if x >= MIN_RR)/len(rr_samples)*100:.1f}%")
    return counts


if __name__ == "__main__":
    run()
