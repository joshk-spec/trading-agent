"""Tests for the short-term reversal backtest.

Same discipline as test_backtest.py: the lookahead guard is the one that
matters, because a backtest that peeks produces beautiful fiction and nothing
in its output reveals it.

    py research/test_backtest_mr.py
"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import Series  # noqa: E402
import backtest_mr as M  # noqa: E402


def series(bars: list[tuple[float, float, float, float, float]]) -> Series:
    s = Series(symbol="X")
    for i, (o, h, l, c, v) in enumerate(bars):
        s.date.append(f"2015-{i // 28 + 1:02d}-{i % 28 + 1:02d}")
        s.o.append(o); s.h.append(h); s.l.append(l); s.c.append(c); s.v.append(v)
    return s


def uptrend_then_dip(n: int = 320, seed: int = 5) -> Series:
    """Rising series with sharp multi-day dips, so RSI(2) actually reaches <5
    while price stays above its 200-SMA — the setup the spec describes.

    The drift must genuinely dominate the dips. A first attempt used 0.22%/day
    against -3%x3 every 37 bars, which nets NEGATIVE: the series fell, sat below
    its 200-SMA almost everywhere, and produced RSI(2)<5 readings that could
    never pass the trend filter. Signals: zero. The vacuity guard below caught
    it; without that guard the lookahead tests would have "passed" on an empty
    set and proven nothing."""
    rnd = random.Random(seed)
    s = Series(symbol="SYN")
    p = 50.0
    for i in range(n):
        drift = -0.030 if (i % 37) in (0, 1, 2) else 0.0050
        p *= (1 + drift + rnd.gauss(0, 0.004))
        p = max(p, 1.0)
        o = p * (1 + rnd.gauss(0, 0.001))
        c = p
        h = max(o, c) * 1.004
        l = min(o, c) * 0.996
        s.date.append(f"{2011 + i // 252}-{(i % 252) // 21 + 1:02d}-{(i % 21) + 1:02d}")
        s.o.append(o); s.h.append(h); s.l.append(l); s.c.append(c)
        s.v.append(9_000_000)
    return s


WIDE = ("1900-01-01", "2999-12-31")


class TestSignalGate(unittest.TestCase):
    def test_synthetic_series_produces_signals(self):
        """Guards the lookahead tests below from passing vacuously."""
        idxs, counts = M.signals_and_funnel(uptrend_then_dip(), WIDE)
        self.assertGreater(len(idxs), 0)
        self.assertEqual(counts[-1], len(idxs))

    def test_gate_counts_never_increase(self):
        _, counts = M.signals_and_funnel(uptrend_then_dip(), WIDE)
        for i in range(1, len(counts)):
            self.assertLessEqual(counts[i], counts[i - 1], M.GATES[i])

    def test_below_the_200_sma_never_signals(self):
        """The trend filter is the only thing separating a dip from a collapse."""
        s = uptrend_then_dip()
        # Force every close under a huge 200-SMA by collapsing the tail.
        for i in range(len(s) - 40, len(s)):
            s.c[i] = 0.01
            s.o[i] = s.h[i] = s.l[i] = 0.01
        idxs, _ = M.signals_and_funnel(s, WIDE)
        self.assertTrue(all(i < len(s) - 40 for i in idxs))

    def test_illiquid_names_are_excluded(self):
        s = uptrend_then_dip()
        for i in range(len(s)):
            s.v[i] = 1.0                      # ADV far below $10M
        idxs, _ = M.signals_and_funnel(s, WIDE)
        self.assertEqual(idxs, [])


class TestNoLookahead(unittest.TestCase):
    def setUp(self):
        self.s = uptrend_then_dip()

    def test_truncating_the_future_does_not_change_past_signals(self):
        full, _ = M.signals_and_funnel(self.s, WIDE)
        self.assertTrue(full)
        for cut in (260, 290, 315):
            trunc = Series(symbol="SYN", date=self.s.date[:cut], o=self.s.o[:cut],
                           h=self.s.h[:cut], l=self.s.l[:cut], c=self.s.c[:cut],
                           v=self.s.v[:cut])
            got, _ = M.signals_and_funnel(trunc, WIDE)
            expected = [i for i in full if i <= cut - 2]
            self.assertEqual([i for i in got if i <= cut - 2], expected,
                             f"signals changed when truncated at {cut}")

    def test_corrupting_future_bars_does_not_change_past_signals(self):
        cut = 280
        full = [i for i in M.signals_and_funnel(self.s, WIDE)[0] if i < cut - 1]
        self.assertTrue(full, "vacuous — no signals before the corruption point")
        t = Series(symbol="SYN", date=list(self.s.date), o=list(self.s.o),
                   h=list(self.s.h), l=list(self.s.l), c=list(self.s.c),
                   v=list(self.s.v))
        for i in range(cut, len(t.date)):
            t.o[i] = t.h[i] = t.l[i] = t.c[i] = 9999.0
            t.v[i] = 1.0
        got = [i for i in M.signals_and_funnel(t, WIDE)[0] if i < cut - 1]
        self.assertEqual(full, got, "future bars leaked into past signals")


class TestExecution(unittest.TestCase):
    """Entry, exit and R accounting against hand-computed values."""

    def _sim(self, after: list, cost_bps: float = 0.0):
        # 6 flat bars (so SMA(5) exists), signal on index 5, entry at 6.
        base = [(100, 101, 99, 100, 1e7)] * 6
        s = series(base + after)
        return M.simulate(s, 5, cost_bps)

    def test_entry_is_the_next_open_not_the_signal_close(self):
        t = self._sim([(97.0, 98, 96, 97.5, 1e7)] * 12)
        self.assertAlmostEqual(t.entry, 97.0)

    def test_disaster_stop_fills_at_the_level(self):
        # entry 100; -15% = 85. Bar 2 trades down to 80 but opens at 99.
        t = self._sim([(100, 101, 99, 100, 1e7), (99, 99.5, 80.0, 84.0, 1e7)])
        self.assertEqual(t.exit_reason, "disaster")
        self.assertAlmostEqual(t.exit_price, 85.0)
        self.assertAlmostEqual(t.r_multiple, -1.0, places=6)

    def test_gap_through_the_disaster_level_fills_worse_than_minus_one_R(self):
        t = self._sim([(100, 101, 99, 100, 1e7), (70.0, 72, 68, 71, 1e7)])
        self.assertEqual(t.exit_reason, "disaster")
        self.assertAlmostEqual(t.exit_price, 70.0)
        self.assertLess(t.r_multiple, -1.0)

    def test_reversion_exit_fills_at_the_following_open(self):
        # Entry 100 flat, then a close far above the 5-day SMA, then a gap up.
        t = self._sim([(100, 101, 99, 100, 1e7)] * 2
                      + [(100, 130, 99, 129.0, 1e7), (120.0, 121, 119, 120, 1e7)])
        self.assertEqual(t.exit_reason, "reverted")
        self.assertAlmostEqual(t.exit_price, 120.0)   # next OPEN, not the close

    def test_time_stop_exits_after_ten_sessions(self):
        # Never reverts (closes stay below the 5-day mean), never hits -15%.
        flat = [(100, 100.2, 99.8, 99.0 - i * 0.05, 1e7) for i in range(20)]
        t = self._sim(flat)
        self.assertEqual(t.exit_reason, "time_stop")
        self.assertLessEqual(t.bars_held, M.MAX_HOLD_SESSIONS + 1)

    def test_r_is_pct_return_over_the_disaster_fraction(self):
        t = self._sim([(100, 101, 99, 100, 1e7)] * 2
                      + [(100, 130, 99, 129.0, 1e7), (110.0, 111, 109, 110, 1e7)])
        self.assertAlmostEqual(t.r_multiple, t.pct_return / M.DISASTER_STOP_PCT,
                               places=9)

    def test_no_tight_stop_exists(self):
        """The specification's central [HARD] rule: a 4% adverse move must NOT
        exit. If a tight stop ever creeps in, this fails."""
        t = self._sim([(100, 101, 96.0, 96.5, 1e7)] * 3
                      + [(100, 130, 99, 129.0, 1e7), (128.0, 129, 127, 128, 1e7)])
        self.assertNotEqual(t.exit_reason, "disaster")
        self.assertGreater(t.r_multiple, 0)


class TestCosts(unittest.TestCase):
    def _r(self, bps):
        base = [(100, 101, 99, 100, 1e7)] * 6
        s = series(base + [(100, 101, 99, 100, 1e7)] * 2
                   + [(100, 130, 99, 129.0, 1e7), (120.0, 121, 119, 120, 1e7)])
        return M.simulate(s, 5, bps).r_multiple

    def test_higher_costs_never_improve_the_result(self):
        prev = None
        for bps in (0, 5, 10, 25, 50, 100):
            r = self._r(bps)
            if prev is not None:
                self.assertLessEqual(r, prev + 1e-12)
            prev = r

    def test_cost_scales_linearly(self):
        d10 = self._r(0) - self._r(10)
        d20 = self._r(0) - self._r(20)
        self.assertAlmostEqual(d20, 2 * d10, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
