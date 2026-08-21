"""funnel.py duplicates every P1 condition from backtest_p1.find_signals so that
a bug in a shared helper could not hide in both. Duplication only stays honest
if something checks the copies still agree — this is that check.

Requires research/data/. Skips (loudly) when the data has not been downloaded,
because a silently-skipped consistency test is worse than no test at all.

    py research/test_funnel.py
"""
from __future__ import annotations

import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_p1 import (  # noqa: E402
    DATA_DIR, BENCHMARK, Indicators, load_bars, find_signals,
)

HAVE_DATA = bool(glob.glob(os.path.join(DATA_DIR, "*.csv")))


@unittest.skipUnless(HAVE_DATA, "no research/data — run: py research/fetch_bars.py")
class TestFunnelAgreesWithEngine(unittest.TestCase):
    def test_final_stage_equals_signal_count(self):
        """funnel's last stage counts bar-days clearing every gate. That must
        equal the number of signals find_signals returns, summed over the
        universe. If these drift, one of the two copies has a bug."""
        import funnel

        counts = funnel.run()
        funnel_total = counts[-1]

        spy = load_bars(os.path.join(DATA_DIR, f"{BENCHMARK}.csv"))
        spy_ind = Indicators(spy)
        spy_idx = {d: i for i, d in enumerate(spy.date)}

        engine_total = 0
        for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
            s = load_bars(path)
            if s.symbol == BENCHMARK or len(s) < 400:
                continue
            engine_total += len(find_signals(s, Indicators(s), spy, spy_ind,
                                             spy_idx, "measured_move"))

        self.assertEqual(
            funnel_total, engine_total,
            f"funnel says {funnel_total} candidates clear every gate but the "
            f"engine produced {engine_total} signals — the duplicated condition "
            f"list has drifted from find_signals()")

    def test_stages_are_monotonically_non_increasing(self):
        """Each gate is a filter, so survivors can never grow from stage to
        stage. A rise means a counter is incremented on the wrong branch."""
        import funnel

        counts = funnel.run()
        for i in range(1, len(counts)):
            self.assertLessEqual(
                counts[i], counts[i - 1],
                f"stage {i} ({funnel.STAGES[i]}) has MORE survivors than "
                f"stage {i-1} ({funnel.STAGES[i-1]}) — miscounted branch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
