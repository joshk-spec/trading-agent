"""Tests for the P1 backtest engine.

The important one is TestNoLookahead. A backtest that peeks at future data
produces beautiful, completely fictional results, and nothing in the output
reveals it. The only defence is proving that a decision made at bar T is
identical whether or not bars after T exist at all.

    py research/test_backtest.py
"""
from __future__ import annotations

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    Series, Indicators, Signal, sma, ema, rsi, atr, roc,
    find_signals, simulate, MAX_GAP_UP,
)


def make_series(symbol: str, bars: list[tuple[float, float, float, float, float]],
                start_day: int = 1) -> Series:
    """bars = [(open, high, low, close, volume), ...] on consecutive fake dates."""
    s = Series(symbol=symbol)
    for i, (o, h, l, c, v) in enumerate(bars):
        # Dates only need to be unique and orderable for the SPY join.
        s.date.append(f"2020-{(start_day + i) // 28 + 1:02d}-{(start_day + i) % 28 + 1:02d}")
        s.o.append(o); s.h.append(h); s.l.append(l); s.c.append(c); s.v.append(v)
    return s


def synthetic_uptrend(n: int = 2400, seed: int = 1) -> Series:
    """A persistent uptrend with periodic shallow pullbacks — the regime P1 is
    designed to trade.

    These parameters were not chosen arbitrarily: a parameter sweep over 243
    combinations of volatility, drift, pullback depth and pullback period found
    only 14 that produce ANY P1 signal, and none producing more than 2 per 900
    bars. P1 is extremely selective, and low daily volatility is what makes it
    fire at all — a tight ATR gives a tight stop, and only a tight stop can
    clear the 2.0 reward:risk minimum against a target that must sit within 8%
    of the 52-week high. Loosen the volatility here and this generator silently
    stops producing signals, which is what `test_the_synthetic_series_actually
    _produces_signals` exists to catch."""
    rnd = random.Random(seed)
    s = Series(symbol="SYN")
    price = 50.0
    for i in range(n):
        drift = -0.010 if (i % 40) < 4 else 0.0018
        price *= (1 + drift + rnd.gauss(0, 0.006))
        price = max(price, 1.0)
        o = price * (1 + rnd.gauss(0, 0.0012))
        c = price
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.002)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, 0.002)))
        v = 5_000_000 * (1 + abs(rnd.gauss(0, 0.3)))
        s.date.append(f"{2016 + i // 252}-{(i % 252) // 21 + 1:02d}-{(i % 21) + 1:02d}")
        s.o.append(o); s.h.append(h); s.l.append(l); s.c.append(c); s.v.append(v)
    return s


def flat_benchmark(dates: list[str]) -> Series:
    """A benchmark that rises very slowly, so the regime filter passes and any
    real uptrend beats it on 20-session relative strength."""
    s = Series(symbol="SPY")
    p = 100.0
    for d in dates:
        p *= 1.0001
        s.date.append(d)
        s.o.append(p); s.h.append(p * 1.001); s.l.append(p * 0.999)
        s.c.append(p); s.v.append(80_000_000)
    return s


class TestIndicators(unittest.TestCase):
    def test_sma_matches_hand_calculation(self):
        self.assertEqual(sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_sma_is_none_until_enough_history(self):
        self.assertEqual(sma([1, 2], 5), [None, None])

    def test_ema_matches_hand_calculation(self):
        # n=3 -> k=0.5; seed = mean(1,2,3) = 2; then 4*.5+2*.5=3; 5*.5+3*.5=4
        out = ema([1, 2, 3, 4, 5], 3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)
        self.assertAlmostEqual(out[4], 4.0)

    def test_rsi_saturates_on_a_pure_uptrend(self):
        out = rsi([float(i) for i in range(1, 40)])
        self.assertAlmostEqual(out[-1], 100.0, places=6)

    def test_rsi_bottoms_on_a_pure_downtrend(self):
        out = rsi([float(i) for i in range(40, 1, -1)])
        self.assertLess(out[-1], 1.0)

    def test_rsi_midrange_on_alternating_equal_moves(self):
        xs = [100.0]
        for i in range(60):
            xs.append(xs[-1] + (1.0 if i % 2 == 0 else -1.0))
        self.assertTrue(45 <= rsi(xs)[-1] <= 55)

    def test_atr_of_constant_range_equals_that_range(self):
        bars = [(10.0, 11.0, 10.0, 10.5)] * 40
        h = [b[1] for b in bars]; l = [b[2] for b in bars]; c = [b[3] for b in bars]
        self.assertAlmostEqual(atr(h, l, c)[-1], 1.0, places=6)

    def test_roc_is_a_simple_percentage_change(self):
        self.assertAlmostEqual(roc([100.0, 0, 0, 0, 110.0], 4)[4], 0.10)


class TestCausality(unittest.TestCase):
    """Every indicator element must depend only on inputs up to that index."""

    def _assert_causal(self, fn, xs):
        full = fn(xs)
        for cut in (len(xs) // 2, len(xs) - 5):
            partial = fn(xs[:cut])
            for i in range(cut):
                if full[i] is None or partial[i] is None:
                    self.assertIs(full[i], partial[i], f"index {i}")
                else:
                    self.assertAlmostEqual(full[i], partial[i], places=9, msg=f"index {i}")

    def test_sma_ema_rsi_roc_are_causal(self):
        rnd = random.Random(3)
        xs = [50 + rnd.gauss(0, 5) for _ in range(200)]
        self._assert_causal(lambda a: sma(a, 20), xs)
        self._assert_causal(lambda a: ema(a, 20), xs)
        self._assert_causal(rsi, xs)
        self._assert_causal(lambda a: roc(a, 20), xs)

    def test_atr_is_causal(self):
        rnd = random.Random(4)
        h, l, c = [], [], []
        p = 50.0
        for _ in range(200):
            p *= 1 + rnd.gauss(0, 0.01)
            c.append(p); h.append(p * 1.01); l.append(p * 0.99)
        full = atr(h, l, c)
        cut = 150
        part = atr(h[:cut], l[:cut], c[:cut])
        for i in range(cut):
            if full[i] is None or part[i] is None:
                self.assertIs(full[i], part[i])
            else:
                self.assertAlmostEqual(full[i], part[i], places=9)


class TestTransactionCosts(unittest.TestCase):
    """Costs must always hurt. A cost model that can flatter a result is worse
    than none, because it launders an optimistic number as a corrected one."""

    def _trade(self, cost_bps):
        bars = [(100, 101, 99, 100, 1e6)] * 3 + [(100, 101, 99, 100.0, 1e6),
                                                 (100.0, 101, 99.5, 100.0, 1e6),
                                                 (100, 125.0, 99.0, 124.0, 1e6),
                                                 (124, 124.5, 80.0, 85.0, 1e6)]
        s = make_series("X", bars)
        sig = Signal("X", 3, s.date[3], 100.0, 90.0, 130.0)
        return simulate(s, Indicators(s), sig, "intraday", cost_bps=cost_bps)

    def test_higher_cost_never_improves_the_result(self):
        prev = None
        for bps in (0, 5, 10, 25, 50, 100):
            r = self._trade(bps).r_multiple
            if prev is not None:
                self.assertLessEqual(r, prev + 1e-12,
                                     f"{bps}bps scored better than the cheaper run")
            prev = r

    def test_zero_cost_matches_the_uncharged_result(self):
        self.assertAlmostEqual(self._trade(0).cost_r, 0.0, places=12)

    def test_cost_is_one_round_trip_not_one_per_partial_exit(self):
        """This trade trims half at +2R and exits the rest later — two exits,
        but still a single entry and a single position. Charging per exit would
        double-count."""
        t = self._trade(10)
        R = 100.0 - 90.0
        self.assertAlmostEqual(t.cost_r, 100.0 * 0.001 / R, places=12)

    def test_cost_scales_linearly_with_bps(self):
        self.assertAlmostEqual(self._trade(20).cost_r, 2 * self._trade(10).cost_r, places=12)

    def test_a_wider_stop_dilutes_the_cost_in_R_terms(self):
        """cost_R = entry*bps/R, so the same dollar cost is a smaller fraction
        of a wider R. Tight-stop strategies are punished hardest by costs, which
        is the real-world effect this is meant to capture."""
        bars = [(100, 101, 99, 100, 1e6)] * 3 + [(100, 101, 99, 100.0, 1e6),
                                                 (100.0, 101, 99.5, 100.0, 1e6),
                                                 (100, 101, 70.0, 75.0, 1e6)]
        s = make_series("X", bars)
        tight = simulate(s, Indicators(s), Signal("X", 3, s.date[3], 100.0, 98.0, 110.0),
                         "intraday", cost_bps=10)
        wide = simulate(s, Indicators(s), Signal("X", 3, s.date[3], 100.0, 90.0, 130.0),
                        "intraday", cost_bps=10)
        self.assertGreater(tight.cost_r, wide.cost_r)


class TestNoLookahead(unittest.TestCase):
    """THE test. Signals found at bar T must not change when bars after T are
    deleted or replaced with nonsense. If this fails, every reported number is
    fiction and the strategy looks better than it is."""

    def setUp(self):
        self.s = synthetic_uptrend()
        self.spy = flat_benchmark(self.s.date)
        self.spy_ind = Indicators(self.spy)
        self.spy_idx = {d: i for i, d in enumerate(self.spy.date)}

    def _signals(self, s: Series) -> list[tuple]:
        ind = Indicators(s)
        sigs = find_signals(s, ind, self.spy, self.spy_ind, self.spy_idx)
        return [(x.idx, round(x.trigger_close, 6), round(x.stop, 6), round(x.target, 6))
                for x in sigs]

    def test_the_synthetic_series_actually_produces_signals(self):
        """Guard against the lookahead test passing vacuously on zero signals."""
        self.assertGreater(len(self._signals(self.s)), 0,
                           "synthetic uptrend produced no signals — the lookahead "
                           "test below would prove nothing")

    def test_truncating_the_future_does_not_change_past_signals(self):
        full = self._signals(self.s)
        # Cuts chosen to sit AFTER known signals (idx 804, 805, 1485) so the
        # comparison is over a non-empty set.
        for cut in (900, 1200, 2000):
            trunc = Series(symbol=self.s.symbol, date=self.s.date[:cut],
                           o=self.s.o[:cut], h=self.s.h[:cut], l=self.s.l[:cut],
                           c=self.s.c[:cut], v=self.s.v[:cut])
            expected = [x for x in full if x[0] <= cut - 2]
            got = [x for x in self._signals(trunc) if x[0] <= cut - 2]
            self.assertEqual(expected, got, f"signals changed when truncated at {cut}")

    def test_corrupting_future_bars_does_not_change_past_signals(self):
        cut = 1600            # after all three known signals
        full = [x for x in self._signals(self.s) if x[0] < cut - 1]
        self.assertTrue(full, "no signals before the corruption point — vacuous test")
        tampered = Series(symbol=self.s.symbol, date=list(self.s.date),
                          o=list(self.s.o), h=list(self.s.h), l=list(self.s.l),
                          c=list(self.s.c), v=list(self.s.v))
        for i in range(cut, len(tampered.date)):
            tampered.o[i] = tampered.h[i] = tampered.l[i] = tampered.c[i] = 9_999.0
            tampered.v[i] = 1.0
        got = [x for x in self._signals(tampered) if x[0] < cut - 1]
        self.assertEqual(full, got, "future bars leaked into past signals")


class TestEntryRules(unittest.TestCase):
    """Fill and gap-void logic at bar idx+1."""

    def _one(self, entry_bar, trigger_close=100.0, stop=95.0, target=115.0):
        # 3 filler bars, the trigger bar, then the entry bar.
        bars = [(100, 101, 99, 100, 1e6)] * 3 + [(100, 101, 99, trigger_close, 1e6), entry_bar]
        s = make_series("X", bars)
        ind = Indicators(s)
        sig = Signal("X", 3, s.date[3], trigger_close, stop, target)
        return simulate(s, ind, sig, "intraday")

    def test_gap_above_2pct_voids_the_trade(self):
        # opens at 102.5 = +2.5% over the trigger close
        self.assertIsNone(self._one((102.5, 103, 102.4, 103, 1e6)))

    def test_gap_within_2pct_that_never_touches_the_limit_does_not_fill(self):
        # opens +1.5% and never trades back down to 100
        self.assertIsNone(self._one((101.5, 102, 101.2, 101.8, 1e6)))

    def test_open_below_trigger_fills_at_the_open(self):
        t = self._one((99.0, 101, 98.5, 100.5, 1e6))
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.entry, 99.0)

    def test_open_above_but_dips_to_the_limit_fills_at_the_limit(self):
        t = self._one((101.0, 101.5, 99.5, 100.2, 1e6))
        self.assertIsNotNone(t)
        self.assertAlmostEqual(t.entry, 100.0)

    def test_fill_that_breaches_the_12pct_stop_rule_is_rejected(self):
        # entry 99 with a stop at 85 is >12% — §6 step 5 re-checks at the fill
        self.assertIsNone(self._one((99.0, 101, 98.5, 100.0, 1e6), stop=85.0, target=200.0))

    def test_fill_that_breaches_the_2R_minimum_is_rejected(self):
        # entry 99, stop 95 -> R=4; target 104 is only 1.25R
        self.assertIsNone(self._one((99.0, 101, 98.5, 100.0, 1e6), stop=95.0, target=104.0))


class TestExitAccounting(unittest.TestCase):
    """R arithmetic. A clean stop is exactly -1R; the +2R trim banks +1.0R."""

    def _run(self, after_entry, stop_model="intraday", stop=90.0, target=130.0):
        # cost_bps=0 deliberately: these tests pin the R ARITHMETIC of the exit
        # rules. Transaction costs are a separate concern with their own tests
        # (TestTransactionCosts); leaving them on here would mean every exit
        # assertion silently encodes the current cost default too, and changing
        # that default would break tests that have nothing to do with costs.
        bars = [(100, 101, 99, 100, 1e6)] * 3 + [(100, 101, 99, 100.0, 1e6),
                                                 (100.0, 101, 99.5, 100.0, 1e6)] + after_entry
        s = make_series("X", bars)
        ind = Indicators(s)
        sig = Signal("X", 3, s.date[3], 100.0, stop, target)
        return simulate(s, ind, sig, stop_model, cost_bps=0.0)

    def test_clean_stop_out_is_exactly_minus_one_R(self):
        # entry 100, stop 90 -> R=10. Next bar trades down through 90.
        t = self._run([(99, 99, 89.0, 89.5, 1e6)])
        self.assertAlmostEqual(t.r_multiple, -1.0, places=6)
        self.assertEqual(t.exit_reason, "stop")

    def test_gap_through_the_stop_loses_more_than_one_R(self):
        # opens at 85, below the 90 stop — the stop-limit cannot fill at 90
        t = self._run([(85.0, 86, 84, 85.5, 1e6)])
        self.assertLess(t.r_multiple, -1.0)
        self.assertAlmostEqual(t.r_multiple, -1.5, places=6)

    def test_two_R_trim_banks_one_R_then_breakeven_stop_keeps_it(self):
        # bar 1 touches 120 (=+2R) -> half off at +2R = +1.0R banked.
        # bar 2 collapses to the breakeven/trailed stop, remainder ~0.
        t = self._run([(100, 120.5, 99.5, 119.0, 1e6),
                       (100, 100.5, 80.0, 85.0, 1e6)])
        self.assertGreaterEqual(t.r_multiple, 0.9)

    def test_stop_is_checked_before_target_within_the_same_bar(self):
        """A bar that spans both the stop and +2R must be scored as the stop —
        we cannot know the intrabar order, so we take the conservative one."""
        t = self._run([(100, 125.0, 88.0, 95.0, 1e6)])
        self.assertEqual(t.exit_reason, "stop")
        self.assertAlmostEqual(t.r_multiple, -1.0, places=6)

    def test_close_model_ignores_an_intraday_dip_that_recovers(self):
        """The two stop models must genuinely differ: a wick through the stop
        that closes above it stops the intraday model out and not the close one."""
        after = [(100, 101, 88.0, 99.0, 1e6),       # wick below 90, closes at 99
                 (99, 100, 98.0, 99.0, 1e6)]
        intraday = self._run(after, stop_model="intraday")
        closed = self._run(after, stop_model="close")
        self.assertEqual(intraday.exit_reason, "stop")
        self.assertNotEqual(closed.exit_reason, "stop")


if __name__ == "__main__":
    unittest.main(verbosity=2)
