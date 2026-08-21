"""Tests for the short-term reversal backtest.

Same discipline as test_backtest.py: the lookahead guard is the one that
matters, because a backtest that peeks produces beautiful fiction and nothing
in its output reveals it.

    py research/test_backtest_mr.py
"""
from __future__ import annotations

import math
import os
import random
import statistics
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
        """The trend filter is the only thing separating a dip from a collapse,
        so it must be tested in isolation.

        An earlier version of this test collapsed the tail to $0.01, which trips
        the $5 minimum-price gate FIRST and never reaches the trend check — it
        passed with the 200-SMA filter entirely removed. The tail here stays
        well above $5 and liquid, and declines hard enough that RSI(2) is deep
        below 5, so the ONLY thing that can suppress a signal is the trend
        filter. If that filter is deleted, this test fails."""
        s = uptrend_then_dip()
        tail = 40
        px = 40.0
        for i in range(len(s) - tail, len(s)):
            px *= 0.97                       # a genuine collapse, not a dip
            s.c[i] = px
            s.o[i] = px * 1.01
            s.h[i] = px * 1.02
            s.l[i] = px * 0.99
            s.v[i] = 9_000_000

        # The tail must genuinely LOOK like a buy to every other gate, or the
        # test proves nothing.
        from backtest_p1 import sma as _sma, rsi as _rsi
        trend, fast = _sma(s.c, M.TREND_SMA), _rsi(s.c, M.RSI_PERIOD)
        tail_idx = range(len(s) - tail + 2, len(s))
        self.assertTrue(all(s.c[i] > M.MIN_PRICE for i in tail_idx),
                        "tail fell below $5 — the price gate would mask the trend gate")
        self.assertTrue(any(fast[i] is not None and fast[i] < M.RSI_THRESHOLD
                            for i in tail_idx),
                        "tail never became oversold — nothing to suppress")
        self.assertTrue(all(trend[i] is not None and s.c[i] <= trend[i]
                            for i in tail_idx),
                        "tail did not fall below its own 200-SMA")

        idxs, _ = M.signals_and_funnel(s, WIDE)
        self.assertFalse([i for i in idxs if i >= len(s) - tail + 2],
                         "signalled below the 200-SMA — the trend filter is not working")

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


def _mk(sym, entry_date, exit_date, r, rsi_v=1.0):
    t = M.MRTrade(sym, entry_date, entry_date, 100.0)
    t.exit_date, t.r_multiple, t.rsi_at_signal = exit_date, r, rsi_v
    return t


class TestSlotAllocation(unittest.TestCase):
    """Without a portfolio cap the backtest books trades the live system could
    never hold — on TRAIN, a median of 17 and a peak of 228 simultaneous
    positions. An average over those is not an executable result."""

    def test_never_exceeds_the_slot_count(self):
        cands = [_mk(f"S{i}", "2015-01-05", "2015-01-20", 0.1) for i in range(50)]
        for slots in (1, 5, 15):
            taken, stats = M.allocate(cands, slots)
            self.assertEqual(len(taken), slots)
            self.assertEqual(stats["skipped"], 50 - slots)

    def test_slots_are_reused_once_positions_close(self):
        cands = [_mk("A", "2015-01-05", "2015-01-06", 0.1),
                 _mk("B", "2015-01-07", "2015-01-08", 0.1),
                 _mk("C", "2015-01-09", "2015-01-10", 0.1)]
        taken, _ = M.allocate(cands, 1)
        self.assertEqual(len(taken), 3)      # sequential, never overlapping

    def test_rsi_tiebreak_takes_the_most_oversold(self):
        cands = [_mk("HI", "2015-01-05", "2015-02-01", 0.0, rsi_v=4.9),
                 _mk("LO", "2015-01-05", "2015-02-01", 0.0, rsi_v=0.2)]
        taken, _ = M.allocate(cands, 1, "rsi")
        self.assertEqual(taken[0].symbol, "LO")

    def test_constraint_actually_binds_on_real_data(self):
        """Regression guard: if this stops binding, the cap has been bypassed."""
        cands, _ = M.candidates(("2015-01-01", "2015-12-31"), 10.0)
        self.assertGreater(len(cands), 50)
        taken, stats = M.allocate(cands, 15)
        self.assertLess(len(taken), len(cands))
        self.assertGreater(stats["skipped"], 0)


class TestDrawdownIsChronological(unittest.TestCase):
    def test_symbol_order_would_understate_drawdown(self):
        """The published -10.9R came from walking trades in SYMBOL order, which
        is not an equity curve. Chronologically it was -94.3R."""
        # Each symbol alternates win-then-loss, so in SYMBOL order the losses
        # are spread out and the curve looks smooth. Chronologically both losses
        # land together in June, which is the real drawdown.
        trades = [_mk("AAA", "2015-01-01", "2015-01-02", +1.0),
                  _mk("AAA", "2015-06-01", "2015-06-02", -1.0),
                  _mk("ZZZ", "2015-01-03", "2015-01-04", +1.0),
                  _mk("ZZZ", "2015-06-03", "2015-06-04", -1.0)]
        def mdd(seq):
            peak = cum = m = 0.0
            for r in seq:
                cum += r; peak = max(peak, cum); m = min(m, cum - peak)
            return m
        as_listed = mdd([t.r_multiple for t in trades])
        chrono = mdd([t.r_multiple for t in sorted(trades, key=lambda t: t.exit_date)])
        self.assertLess(chrono, as_listed)   # the real curve is worse


class TestClusteredT(unittest.TestCase):
    def test_same_day_trades_count_as_one_observation(self):
        """20 copies of one day's outcome must not look like 20 observations."""
        many = [_mk(f"S{i}", "2015-01-05", "2015-01-09", 0.10) for i in range(20)]
        many += [_mk(f"T{i}", "2015-02-05", "2015-02-09", -0.02) for i in range(20)]
        t_cl, n_days = M.clustered_t(many)
        self.assertEqual(n_days, 2)
        naive_n = len(many)
        self.assertLess(n_days, naive_n)

    def test_n_is_distinct_days_not_trade_count_on_real_data(self):
        """The correction is about the DENOMINATOR, not the direction.

        Clustering does not monotonically shrink t -- it removes a dependence
        assumption, and the result can move either way depending on how the
        within-day and between-day variances compare. On the full TRAIN it cut
        +9.91 to +3.47; on a two-year slice it moves the other way. Asserting
        "smaller" would encode a claim that is simply not true, so this pins
        the mechanism instead."""
        trades, _ = M.run(("2015-01-01", "2016-12-31"), 10.0, 15)
        self.assertGreater(len(trades), 50)
        _, n_days = M.clustered_t(trades)
        distinct = len({t.entry_date for t in trades})
        self.assertEqual(n_days, distinct)
        self.assertLess(n_days, len(trades))


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
