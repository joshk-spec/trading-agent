"""Hypotheses under test, one function per mechanism.

Each strategy supplies (a) a signal generator and (b) the ExitRules its
mechanism implies. Everything else — fills, the gap rule, stops, trailing,
costs, R accounting — comes from the single tested engine in backtest_p1.py.
That is deliberate: a second copy of the exit logic per strategy is exactly how
this repo ended up with two documents that disagreed about what a stop was.

Every strategy here must have a committed pre-registration in
research/preregistered/ BEFORE it is run. The commit timestamp is the evidence
that the hypothesis preceded the result.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    Series, Indicators, Signal, ExitRules,
    sma, rsi, atr,
    MIN_PRICE, MIN_ADV_DOLLARS, SMA_SLOW,
)


@dataclass(frozen=True)
class Strategy:
    name: str
    hypothesis_id: str
    exits: ExitRules
    signals: Callable[[Series, Indicators], list[Signal]]
    # Extra series the engine's Indicators must build for this strategy's exits.
    ema_exit_period: int = 20
    sma_exit_period: int = 0


# ───────────────────── H001 — mean reversion after forced selling ─────────────────────
# Pre-registration: research/preregistered/001_mean_reversion_oversold.md
H001_RSI_PERIOD   = 2
H001_RSI_MAX      = 5.0
H001_DOWN_DAYS    = 3
H001_ATR_MULT     = 2.5
H001_TARGET_SMA   = 20
H001_EXIT_SMA     = 5
H001_MAX_HOLD     = 10


def h001_signals(s: Series, ind: Indicators) -> list[Signal]:
    """Liquid name in an intact uptrend, sold down hard over several sessions.

    Buys weakness, unlike P1 which bought strength. The claim is narrow: a
    2-4 day dislocation closes back toward the 20-day mean. It does not require
    the trend to continue, only the dislocation to resolve."""
    fast_rsi = rsi(s.c, H001_RSI_PERIOD)
    sma20 = sma(s.c, H001_TARGET_SMA)
    atr14 = ind.atr
    out: list[Signal] = []

    start = SMA_SLOW + 2
    for i in range(start, len(s) - 1):
        if s.c[i] < MIN_PRICE:
            continue
        if ind.adv[i] is None or ind.adv[i] < MIN_ADV_DOLLARS:
            continue

        # Trend intact — buy dips, never falling knives.
        slow = ind.sma_slow[i]
        if slow is None or s.c[i] <= slow:
            continue

        # Short-horizon oversold. RSI(2), not RSI(14): a 14-day window cannot
        # resolve the 2-4 day dislocation this mechanism is about.
        r = fast_rsi[i]
        if r is None or r >= H001_RSI_MAX:
            continue

        # Consecutive lower closes — a slide, not one bad print.
        if any(s.c[i - k] >= s.c[i - k - 1] for k in range(H001_DOWN_DAYS)):
            continue

        a = atr14[i]
        tgt = sma20[i]
        if a is None or tgt is None:
            continue

        stop = s.c[i] - H001_ATR_MULT * a
        if stop <= 0 or stop >= s.c[i]:
            continue
        # The mean must actually be above the price, or there is no dislocation
        # left to close and the trade has no objective.
        if tgt <= s.c[i]:
            continue

        out.append(Signal(s.symbol, i, s.date[i], s.c[i], stop, tgt))
    return out


H001 = Strategy(
    name="mean reversion after forced selling",
    hypothesis_id="H001",
    signals=h001_signals,
    sma_exit_period=H001_EXIT_SMA,
    exits=ExitRules(
        stop_model="intraday",
        # None of P1's trend-riding machinery applies: this is not a trend trade.
        breakeven_at_1r=False,
        trim_half_at_2r=False,
        trail_atr_mult=0.0,
        ema_exit_consecutive=0,
        time_stop_sessions=0,
        # The objective is the mean, taken whole when reached.
        exit_at_target=True,
        exit_when_close_above_sma=H001_EXIT_SMA,
        max_hold_sessions=H001_MAX_HOLD,
        # P1's 2.0 minimum reward:risk is a structural-target rule. This target
        # is a mean-reversion objective, so the ratio carries no information
        # here and enforcing it would reject the hypothesis rather than test it.
        enforce_min_rr=False,
        # The 12%-of-entry stop rejection STAYS ON. The pre-registration is
        # silent on it; keeping a risk control is the conservative reading, and
        # it only ever removes the most volatile setups.
        enforce_max_stop_pct=True,
    ),
)


ALL: dict[str, Strategy] = {s.hypothesis_id: s for s in (H001,)}
