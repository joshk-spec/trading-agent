"""Which P1 gates carry the edge, and which only restrict frequency?

P1's gates admit 341 of 239,917 bar-days — 0.14%. That selectivity is why P1
can never accumulate enough trades to validate itself: at 5.8 trades/year,
confirming a realistic +0.10R edge would need ~884 trades, or 152 years. If
some gate is costing frequency without contributing edge, relaxing it buys
statistical power for free. If every gate is load-bearing, that is an answer
too — and it means P1 is unvalidatable by construction.

PROTOCOL — declared here before any result was looked at, because testing 15
variants on one dataset will always turn up a winner by luck, and the 20-EMA
study in FINDINGS.md already showed an in-sample "improvement" that inverted
out of sample.

  1. Every variant relaxes exactly ONE gate. No combinations, no search.
  2. All tuning happens on the TRAIN window (signals dated 2011-01-01 to
     2019-12-31). The TEST window (2020-01-01 onward) is not consulted until
     step 4.
  3. Advancement is decided by criteria fixed in advance:
        (a) at least 3x the baseline trade count, AND
        (b) train average R >= 0.
     A variant that only improves R without adding trades does not solve the
     problem this study exists to solve.
  4. Only advancing variants are then run once on TEST. Whatever that shows is
     the result — no re-tuning afterwards.
  5. With 15 hypotheses, a nominal |t| > 1.96 means nothing. The Bonferroni
     threshold is alpha = 0.05/15 = 0.0033, i.e. |t| > 2.94. Anything below
     that is reported as noise regardless of how good the average looks.

    py research/gate_study.py
"""
from __future__ import annotations

import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import Config, DEFAULT_CONFIG, run  # noqa: E402

TRAIN = ("2011-01-01", "2019-12-31")
TEST = ("2020-01-01", "2026-12-31")

MIN_TRADE_MULTIPLE = 3.0
BONFERRONI_T = 2.94

# Each entry relaxes ONE gate. Order is arbitrary and fixed before results.
VARIANTS: list[tuple[str, Config]] = [
    ("baseline (playbook)",            DEFAULT_CONFIG),
    ("within 15% of high (was 8%)",    Config(max_pct_below_high=0.15)),
    ("within 25% of high",             Config(max_pct_below_high=0.25)),
    ("retracement 2-15% (was 3-10%)",  Config(retrace_min=0.02, retrace_max=0.15)),
    ("retracement gate off",           Config(retrace_min=0.0, retrace_max=1.0)),
    ("RSI band 35-65 (was 40-55)",     Config(rsi_lo=35.0, rsi_hi=65.0)),
    ("RSI band gate off",              Config(rsi_lo=0.0, rsi_hi=100.0)),
    ("20-EMA proximity 5% (was 2%)",   Config(ema_proximity=0.05)),
    ("20-EMA proximity gate off",      Config(ema_proximity=10.0)),
    ("declining-volume gate off",      Config(require_declining_vol=False)),
    ("relative-strength gate off",     Config(require_rel_strength=False)),
    ("trigger-volume gate off",        Config(require_trigger_volume=False)),
    ("50-SMA slope gate off",          Config(require_sma_slope=False)),
    ("min reward:risk 1.5 (was 2.0)",  Config(min_rr=1.5)),
    ("min reward:risk 1.0",            Config(min_rr=1.0)),
    ("SPY regime gate off",            Config(require_regime=False)),
]


def stats(res: dict) -> tuple[int, float, float, float]:
    rs = [t.r_multiple for t in res["trades"]]
    n = len(rs)
    if n < 2:
        return n, 0.0, 0.0, 0.0
    avg = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    t = avg / (sd / math.sqrt(n)) if sd else 0.0
    win = sum(1 for r in rs if r > 0) / n * 100
    return n, avg, win, t


def evaluate(cfg: Config, window: tuple[str, str]) -> tuple[int, float, float, float]:
    return stats(run("intraday", "measured_move", window[0], window[1], cfg=cfg))


def main() -> None:
    print(__doc__.split("PROTOCOL")[0].strip())
    print("\n" + "=" * 76)
    print(f"TRAIN  signals {TRAIN[0]} .. {TRAIN[1]}   (all tuning happens here)")
    print("=" * 76)
    print(f"  {'variant':<34}{'trades':>8}{'avg R':>9}{'win%':>7}{'t':>7}  advance?")

    base_n, base_avg, _, _ = evaluate(DEFAULT_CONFIG, TRAIN)
    advancing: list[tuple[str, Config, int, float]] = []

    for name, cfg in VARIANTS:
        n, avg, win, t = evaluate(cfg, TRAIN)
        adv = ""
        if cfg is not DEFAULT_CONFIG:
            enough_trades = base_n > 0 and n >= base_n * MIN_TRADE_MULTIPLE
            non_negative = avg >= 0
            if enough_trades and non_negative:
                adv = "YES"
                advancing.append((name, cfg, n, avg))
            elif not enough_trades and non_negative:
                adv = "no (too few trades)"
            elif enough_trades:
                adv = "no (negative R)"
            else:
                adv = "no"
        print(f"  {name:<34}{n:>8}{avg:>+9.3f}{win:>7.1f}{t:>+7.2f}  {adv}")

    print(f"\n  baseline trade count on TRAIN: {base_n}; "
          f"advancement needs >= {base_n * MIN_TRADE_MULTIPLE:.0f} trades AND avg R >= 0")

    print("\n" + "=" * 76)
    print(f"TEST  signals {TEST[0]} .. {TEST[1]}   (consulted once, no re-tuning)")
    print("=" * 76)
    if not advancing:
        print("  No variant met the pre-declared advancement criteria.")
        print("  Nothing is validated out of sample, and nothing is recommended.")
    else:
        print(f"  {'variant':<34}{'trades':>8}{'avg R':>9}{'win%':>7}{'t':>7}  verdict")
        for name, cfg, _, _ in advancing:
            n, avg, win, t = evaluate(cfg, TEST)
            if avg > 0 and abs(t) > BONFERRONI_T:
                verdict = "survives"
            elif avg > 0:
                verdict = f"positive but |t|<{BONFERRONI_T} = noise"
            else:
                verdict = "fails (negative)"
            print(f"  {name:<34}{n:>8}{avg:>+9.3f}{win:>7.1f}{t:>+7.2f}  {verdict}")

    # Frequency context: what any of this would mean for validation time.
    print("\n" + "=" * 76)
    print("FREQUENCY CONTEXT")
    print("=" * 76)
    full_n, _, _, _ = evaluate(DEFAULT_CONFIG, ("", ""))
    yrs = 15
    print(f"  baseline: {full_n} trades over ~{yrs}y = {full_n/yrs:.1f}/yr across 69 names")
    print(f"  detecting a +0.10R edge needs ~884 trades "
          f"= {884/(full_n/yrs):.0f} years at that rate")


if __name__ == "__main__":
    main()
