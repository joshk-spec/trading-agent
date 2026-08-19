"""Unit tests for risk_engine. Stdlib only — no pytest needed.

    python3 engine/test_risk_engine.py          (from project root)
    python3 -m unittest discover engine -v

Every constitutional number is pinned here. A failing test means either the
engine drifted or CLAUDE.md changed without the engine following.
"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk_engine import (  # noqa: E402
    Position, resolve_tier, playbooks_for, playbook_allowed, max_risk_trade,
    symbol_exposure, check_caps, size_equity, size_long_option, size_csp,
    count_day_trades, day_trades_available, check_drawdown,
    check_option_liquidity, MAX_OPTIONS_EXP_PCT,
)


class TestTiers(unittest.TestCase):
    def test_boundaries_are_exact(self):
        cases = [
            (0, "T0"), (49.99, "T0"), (699.99, "T0"),
            (700.0, "T1"), (2_499.99, "T1"),
            (2_500.0, "T2"), (9_999.99, "T2"),
            (10_000.0, "T3"), (24_999.99, "T3"),
            (25_000.0, "T4"), (1_000_000, "T4"),
        ]
        for value, tier in cases:
            with self.subTest(value=value):
                self.assertEqual(resolve_tier(value), tier)

    def test_playbook_gating_matches_tiers(self):
        self.assertEqual(playbooks_for(500), ("P1",))
        self.assertEqual(playbooks_for(1_000), ("P1", "P2"))
        self.assertEqual(playbooks_for(15_000), ("P1", "P2", "P3"))
        self.assertEqual(playbooks_for(30_000), ("P1", "P2", "P3", "P4"))
        self.assertFalse(playbook_allowed(500, "P2"))
        self.assertFalse(playbook_allowed(24_999, "P4"))
        self.assertTrue(playbook_allowed(25_000, "P4"))

    def test_p4_uses_reduced_risk_budget(self):
        self.assertEqual(max_risk_trade(100_000, "P1"), 5_000)
        self.assertEqual(max_risk_trade(100_000, "P4"), 2_000)


class TestMinimumViableUnit(unittest.TestCase):
    """§2.3 — the rule that governs everything at small account sizes."""

    def test_t0_account_cannot_buy_any_option(self):
        r = size_long_option(100, premium=0.335, playbook="P2")
        self.assertFalse(r.ok)
        self.assertIn("not unlocked", r.reasons[0])

    def test_mvu_blocks_when_one_contract_exceeds_budget(self):
        r = size_long_option(700, premium=0.50, playbook="P2")
        self.assertFalse(r.ok)
        self.assertIn("MINIMUM VIABLE UNIT", r.reasons[0])

    def test_mvu_never_rounds_up_to_one(self):
        for acct in (700, 1_000, 2_000):
            with self.subTest(acct=acct):
                r = size_long_option(acct, premium=2.00, playbook="P2")
                if not r.ok:
                    self.assertEqual(r.quantity, 0, "must return 0, never round up")

    def test_valid_case_matches_hand_calculation(self):
        r = size_long_option(3_000, premium=1.40, playbook="P2")
        self.assertTrue(r.ok)
        self.assertEqual(r.quantity, 1)          # floor(150/140)
        self.assertEqual(r.notional, 140.0)
        self.assertEqual(r.risk_dollars, 140.0)  # long option max loss = premium
        self.assertAlmostEqual(r.risk_pct, 140 / 3000, places=9)

    def test_t1_single_contract_cap(self):
        self.assertTrue(size_long_option(1_000, premium=0.40, playbook="P2").ok)
        self.assertFalse(size_long_option(1_000, premium=2.10, playbook="P2").ok)


class TestEquitySizing(unittest.TestCase):
    def test_notional_cap_binds_before_risk_target(self):
        r = size_equity(1_000, entry=14.50, stop=13.60)
        self.assertTrue(r.ok)
        self.assertEqual(r.binding_constraint, "MAX_POS_NOTIONAL")
        self.assertAlmostEqual(r.notional, 250.0, places=2)
        self.assertLess(r.risk_pct, 0.05)

    def test_p1_realized_risk_ceiling_is_3pct_not_5pct(self):
        """FINDING F6: P1 rejects stops wider than 12% and caps notional at 25%,
        so realized risk can never exceed 0.25 * 0.12 = 3%. The documented 5%
        target is unreachable on P1 by construction."""
        worst = 0.0
        for i in range(5, 121):
            stop_pct = i / 1000
            r = size_equity(10_000, entry=100.0, stop=100.0 * (1 - stop_pct))
            if r.ok:
                worst = max(worst, r.risk_pct)
        self.assertLessEqual(worst, 0.03 + 1e-9, f"exceeded 3%: {worst:.4%}")
        self.assertAlmostEqual(worst, 0.03, places=4)

    def test_rejects_stop_wider_than_12_percent(self):
        r = size_equity(10_000, entry=100.0, stop=87.0)
        self.assertFalse(r.ok)
        self.assertIn("too volatile", r.reasons[0])

    def test_rejects_inverted_stop(self):
        self.assertFalse(size_equity(10_000, entry=100.0, stop=105.0).ok)

    def test_blocked_below_account_floor(self):
        r = size_equity(49.0, entry=10.0, stop=9.5)
        self.assertFalse(r.ok)
        self.assertIn("floor", r.reasons[0])


class TestSymbolExposure(unittest.TestCase):
    """FINDING F2 — the cap no playbook computed."""

    def test_aggregates_equity_and_options(self):
        pos = [
            Position("F", "equity", 100, 1_450.0),
            Position("F", "long_option", 2, 300.0),
            Position("SOFI", "equity", 50, 900.0),
        ]
        self.assertEqual(symbol_exposure(pos, "F"), 1_750.0)
        self.assertEqual(symbol_exposure(pos, "f"), 1_750.0)
        self.assertEqual(symbol_exposure(pos, "NVDA"), 0.0)

    def test_blocks_position_that_would_breach_30pct(self):
        pos = [
            Position("F", "equity", 100, 1_450.0),
            Position("F", "long_option", 5, 1_500.0),
        ]
        v = check_caps(10_000, pos, "F", add_notional=200.0, is_option=True)
        self.assertTrue(any("MAX_SYMBOL_EXP" in x for x in v))

    def test_equity_sizing_trims_to_remaining_symbol_room(self):
        pos = [Position("F", "equity", 190, 2_800.0)]     # 28% of 10k
        r = size_equity(10_000, entry=14.50, stop=13.60, symbol="F", positions=pos)
        self.assertTrue(r.ok)
        self.assertEqual(r.binding_constraint, "MAX_SYMBOL_EXP")
        self.assertAlmostEqual(r.notional, 200.0, places=2)


class TestOptionsExposureAndCSP(unittest.TestCase):
    """FINDING F1 — P3 claimed CSPs could reach 50% while the constitution
    capped all options exposure at 40%."""

    def test_csp_collateral_counts_toward_global_options_cap(self):
        pos = [Position("SOFI", "short_put", 3, 5_400.0)]   # 27% of 20k
        v = check_caps(20_000, pos, "F", add_notional=3_000.0, is_option=True)
        self.assertTrue(any("MAX_OPTIONS_EXP" in x for x in v))

    def test_no_path_allows_options_above_40_percent(self):
        acct, pos, total = 20_000, [], 0.0
        for i in range(10):
            r = size_csp(acct, cash_available=1e9, strike=25.0,
                         symbol=f"S{i}", positions=pos)
            if not r.ok:
                break
            pos.append(Position(f"S{i}", "short_put", r.quantity, r.notional))
            total += r.notional
        self.assertLessEqual(total, acct * MAX_OPTIONS_EXP_PCT + 1e-6)

    def test_rejects_underlying_too_expensive(self):
        r = size_csp(10_000, cash_available=10_000, strike=76.90)
        self.assertFalse(r.ok)
        self.assertIn("too expensive", r.reasons[0])

    def test_requires_actual_cash(self):
        self.assertFalse(size_csp(20_000, cash_available=100.0, strike=25.0).ok)

    def test_locked_below_t3(self):
        self.assertFalse(size_csp(5_000, cash_available=5_000, strike=14.5).ok)
        self.assertTrue(size_csp(10_000, cash_available=10_000, strike=14.5).ok)


class TestConcurrency(unittest.TestCase):
    def test_blocks_sixth_position(self):
        pos = [Position(f"S{i}", "equity", 1, 100.0) for i in range(5)]
        v = check_caps(100_000, pos, "NEW", add_notional=100.0, is_option=False)
        self.assertTrue(any("MAX_CONCURRENT" in x for x in v))


class TestPatternDayTrader(unittest.TestCase):
    def test_window_spans_weekend_correctly(self):
        today = date(2026, 8, 19)                # Wednesday
        log = [
            {"date": "2026-08-13"},   # boundary, in window
            {"date": "2026-08-12"},   # 6 business days back, OUT
            {"date": "2026-08-17"},
            {"date": "2026-08-19"},
        ]
        self.assertEqual(count_day_trades(log, today), 3)

    def test_available_count_and_exemption(self):
        today = date(2026, 8, 19)
        log = [{"date": "2026-08-17"}, {"date": "2026-08-18"}]
        self.assertEqual(day_trades_available(10_000, log, today), 1)
        self.assertEqual(day_trades_available(24_999, log, today), 1)
        self.assertEqual(day_trades_available(25_000, log, today), 999)
        log.append({"date": "2026-08-19"})
        self.assertEqual(day_trades_available(10_000, log, today), 0)


class TestDrawdown(unittest.TestCase):
    def test_daily_halt_triggers_at_exactly_10pct(self):
        self.assertTrue(check_drawdown(900.0, 1_000.0, 1_000.0).halt)
        self.assertFalse(check_drawdown(900.01, 1_000.0, 1_000.0).halt)

    def test_weekly_halt_says_operator_must_clear(self):
        d = check_drawdown(800.0, 850.0, 1_000.0)
        self.assertTrue(d.halt)
        self.assertTrue(any("OPERATOR MUST CLEAR" in r for r in d.reasons))

    def test_account_floor_halts(self):
        self.assertTrue(check_drawdown(49.0, 49.0, 49.0).halt)


class TestLiquidityGates(unittest.TestCase):
    """Pinned against real quotes captured 2026-08-19."""

    def test_real_spy_contract_passes(self):
        v = check_option_liquidity(28_878, 41_920, 1.98, 2.00, 1.99, 1, 110)
        self.assertEqual(v, [])

    def test_real_f_contract_passes(self):
        v = check_option_liquidity(41_942, 5_056, 0.33, 0.34, 0.335, 1, 271)
        self.assertEqual(v, [])

    def test_wide_spread_rejected(self):
        v = check_option_liquidity(5_000, 500, 0.25, 0.35, 0.30, 1, 100)
        self.assertTrue(any("spread" in x for x in v))

    def test_zero_bid_rejected(self):
        v = check_option_liquidity(2_000, 500, 0.0, 0.05, 0.03, 1, 100)
        self.assertTrue(any("bid is zero" in x for x in v))

    def test_thin_ask_size_rejected(self):
        v = check_option_liquidity(41_942, 5_056, 0.33, 0.34, 0.335, 5, 12)
        self.assertTrue(any("ask_size" in x for x in v))


if __name__ == "__main__":
    unittest.main(verbosity=2)
