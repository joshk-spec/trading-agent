"""Unit tests for risk_engine. Stdlib only — no pytest needed.

    python3 engine/test_risk_engine.py          (from project root)
    python3 -m unittest discover engine -v

Every constitutional number is pinned here. A failing test means either the
engine drifted or CLAUDE.md changed without the engine following.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk_engine import (  # noqa: E402
    Position, resolve_tier, playbooks_for, playbook_allowed, max_risk_trade,
    symbol_exposure, check_caps, size_equity, size_long_option, size_csp,
    count_day_trades, day_trades_available, check_drawdown,
    check_option_liquidity, load_positions, MAX_OPTIONS_EXP_PCT,
)

ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_engine.py")


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
        # 250/14.50 = 17.24 shares, floored to 17 whole shares so a broker-side
        # stop can be placed. At or under the $250 cap, never over.
        self.assertEqual(r.quantity, 17.0)
        self.assertAlmostEqual(r.notional, 246.50, places=2)
        self.assertLessEqual(r.notional, 250.0 + 1e-9)
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
        # $200 of room / 14.50 = 13.79 shares, floored to 13 whole shares.
        self.assertEqual(r.quantity, 13.0)
        self.assertLessEqual(r.notional, 200.0 + 1e-9)


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

    def test_missing_marks_are_reported_not_silently_passed(self):
        """halt=False with a missing mark means 'never asked', not 'all clear'.
        The preflight CLI defaults both marks to 0.0, so without this the
        primary drawdown safety mechanism disables itself silently."""
        d = check_drawdown(1_000.0, 0.0, 0.0)
        self.assertFalse(d.halt)
        self.assertEqual(len(d.checks_skipped), 2)
        self.assertTrue(any("DAILY_HALT not evaluated" in s for s in d.checks_skipped))
        self.assertTrue(any("WEEKLY_HALT not evaluated" in s for s in d.checks_skipped))

    def test_present_current_marks_skip_nothing(self):
        today = date(2026, 8, 20)          # Thursday
        d = check_drawdown(1_000.0, 1_000.0, 1_000.0,
                           session_open_date=today, week_open_date=today, today=today)
        self.assertEqual(d.checks_skipped, [])

    def test_one_missing_mark_reports_only_that_one(self):
        today = date(2026, 8, 20)
        d = check_drawdown(1_000.0, 1_000.0, 0.0,
                           session_open_date=today, week_open_date=today, today=today)
        self.assertEqual(len(d.checks_skipped), 1)
        self.assertIn("WEEKLY_HALT", d.checks_skipped[0])


class TestStaleMarks(unittest.TestCase):
    """A mark left over from an earlier session measures drawdown against the
    wrong baseline and reports a clean pass while doing it — the same silent
    failure as a missing mark, so it is blocking in the same way."""

    def test_yesterdays_session_mark_is_stale(self):
        today = date(2026, 8, 20)
        d = check_drawdown(1_000.0, 1_000.0, 1_000.0,
                           session_open_date=date(2026, 8, 19),   # yesterday
                           week_open_date=today, today=today)
        self.assertFalse(d.halt)
        self.assertEqual(len(d.checks_skipped), 1)
        self.assertIn("DAILY_HALT baseline is STALE", d.checks_skipped[0])

    def test_week_mark_from_previous_week_is_stale(self):
        today = date(2026, 8, 20)                       # Thu, week of Mon 8/17
        d = check_drawdown(1_000.0, 1_000.0, 1_000.0,
                           session_open_date=today,
                           week_open_date=date(2026, 8, 14),      # Fri of prior week
                           today=today)
        self.assertEqual(len(d.checks_skipped), 1)
        self.assertIn("WEEKLY_HALT baseline is STALE", d.checks_skipped[0])

    def test_week_mark_from_monday_is_current_all_week(self):
        monday = date(2026, 8, 17)
        for offset in range(5):                          # Mon-Fri of that week
            today = monday + timedelta(days=offset)
            with self.subTest(today=today):
                d = check_drawdown(1_000.0, 1_000.0, 1_000.0,
                                   session_open_date=today,
                                   week_open_date=monday, today=today)
                self.assertEqual(d.checks_skipped, [])

    def test_absent_dates_are_blocking_not_silently_trusted(self):
        """Omitting the dates must not be the quiet way to skip the check —
        that is the exact trap the missing-mark rule already closed."""
        d = check_drawdown(1_000.0, 1_000.0, 1_000.0, today=date(2026, 8, 20))
        self.assertEqual(len(d.checks_skipped), 2)
        self.assertTrue(all("staleness unverified" in s for s in d.checks_skipped))

    def test_stale_mark_still_reports_a_real_breach(self):
        """Staleness is blocking, but a breach it does detect is still real —
        the two signals must not mask each other."""
        today = date(2026, 8, 20)
        d = check_drawdown(800.0, 1_000.0, 1_000.0,
                           session_open_date=date(2026, 8, 19), week_open_date=today,
                           today=today)
        self.assertTrue(d.halt)
        self.assertTrue(any("DAILY_HALT breached" in r for r in d.reasons))
        self.assertTrue(any("STALE" in s for s in d.checks_skipped))

    def test_cli_reports_stale_session_mark(self):
        result = subprocess.run(
            [sys.executable, ENGINE_PATH, "preflight", "--account", "50",
             "--session-open", "50", "--week-open", "50",
             "--session-open-date", "2000-01-01", "--week-open-date", "2000-01-01"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertFalse(out["halt"])
        self.assertEqual(len(out["checks_skipped"]), 2)
        self.assertTrue(any("STALE" in s for s in out["checks_skipped"]))


class TestEquityQuantityPrecision(unittest.TestCase):
    """A cap that binds must not be undone by presentation rounding."""

    def test_quantity_is_floored_so_notional_never_exceeds_cap(self):
        r = size_equity(10_000.0, 14.5077, 13.6, "F")
        self.assertTrue(r.ok)
        cap = 10_000.0 * 0.25
        self.assertLessEqual(r.notional, cap + 0.01)
        # quantity must be representable at the broker's 6dp precision
        self.assertEqual(r.quantity, round(r.quantity, 6))

    def test_reported_risk_matches_the_floored_quantity(self):
        r = size_equity(10_000.0, 14.5077, 13.6, "F")
        expected = r.quantity * (14.5077 - 13.6)
        self.assertAlmostEqual(r.risk_dollars, round(expected, 2), places=2)


class TestStopEligibility(unittest.TestCase):
    """§6 step 9 requires a broker-side stop, which Robinhood rejects on
    fractional quantities. The engine reports this rather than the agent eyeballing it."""

    def test_whole_share_position_is_preferred_so_a_stop_can_be_placed(self):
        """Raw sizing (2_500/14.50 = 172.41) is fractional, and a fractional
        position cannot carry a broker-side stop. Flooring to 172 whole shares
        costs 0.41 shares of exposure and buys real intraday protection."""
        r = size_equity(10_000.0, 14.50, 13.60, "F")
        self.assertTrue(r.ok)
        self.assertEqual(r.quantity, 172.0)
        self.assertTrue(float(r.quantity).is_integer())
        self.assertTrue(r.stop_eligible)

    def test_whole_share_quantity_is_stop_eligible(self):
        # 25% of 10_000 = 2_500 notional / entry 25.00 = exactly 100 shares
        r = size_equity(10_000.0, 25.00, 23.00, "F")
        self.assertTrue(r.ok)
        self.assertEqual(r.quantity, 100.0)
        self.assertTrue(r.stop_eligible)

    def test_sub_one_share_stays_fractional_and_says_it_is_unprotected(self):
        """A $50 account cannot afford one whole share of a $14.50 stock at a
        25% notional cap. It is not rounded up to 1 (that would breach the cap)
        — it stays fractional and reports that no stop can be placed."""
        r = size_equity(50.0, 14.50, 13.60, "F")
        self.assertTrue(r.ok)
        self.assertLess(r.quantity, 1.0)
        self.assertFalse(r.stop_eligible)
        self.assertLessEqual(r.notional, 12.5 + 1e-9)

    def test_flooring_to_whole_shares_never_exceeds_a_cap(self):
        """Flooring only ever reduces size, so every cap enforced before it
        still holds afterward — across a wide sweep of prices and accounts."""
        for account in (200.0, 1_000.0, 5_000.0, 25_000.0):
            for entry in (7.30, 14.50, 63.75, 249.99):
                with self.subTest(account=account, entry=entry):
                    r = size_equity(account, entry, entry * 0.93, "F")
                    if not r.ok:
                        continue
                    self.assertLessEqual(r.notional, account * 0.25 + 1e-9)
                    self.assertLessEqual(r.risk_pct, 0.03 + 1e-9)
                    if r.quantity >= 1:
                        self.assertTrue(float(r.quantity).is_integer())
                        self.assertTrue(r.stop_eligible)

    def test_option_contracts_are_always_stop_eligible(self):
        r = size_long_option(10_000.0, 1.40, "F")
        self.assertTrue(r.ok)
        self.assertTrue(r.stop_eligible)


class TestMinimumRewardRisk(unittest.TestCase):
    """P1's [HARD] 2.0 minimum R:R was prose-only; the engine now enforces it."""

    def test_target_below_2r_is_rejected(self):
        r = size_equity(10_000.0, 14.50, 13.60, "F", (), 15.40)  # 1.0R
        self.assertFalse(r.ok)
        self.assertTrue(any("reward:risk" in x for x in r.reasons))

    def test_target_at_exactly_2r_is_accepted(self):
        r = size_equity(10_000.0, 14.50, 13.60, "F", (), 16.30)  # exactly 2.0R
        self.assertTrue(r.ok, r.reasons)

    def test_target_above_2r_is_accepted(self):
        r = size_equity(10_000.0, 14.50, 13.60, "F", (), 18.00)
        self.assertTrue(r.ok, r.reasons)

    def test_omitted_target_skips_the_check(self):
        self.assertTrue(size_equity(10_000.0, 14.50, 13.60, "F").ok)

    def test_target_below_entry_is_rejected(self):
        r = size_equity(10_000.0, 14.50, 13.60, "F", (), 14.00)
        self.assertFalse(r.ok)
        self.assertTrue(any("must be above entry" in x for x in r.reasons))


class TestLoadPositions(unittest.TestCase):
    """load_positions() is what closes the gap where the CLI never enforced
    MAX_SYMBOL_EXP/MAX_CONCURRENT because it never saw existing positions."""

    def test_missing_file_means_no_open_positions(self):
        self.assertEqual(load_positions("this/path/does/not/exist.json"), [])

    def test_loads_valid_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"positions": [
                {"symbol": "F", "kind": "equity", "quantity": 100, "notional": 1450.0},
            ]}, f)
            path = f.name
        try:
            pos = load_positions(path)
            self.assertEqual(len(pos), 1)
            self.assertEqual(pos[0].symbol, "F")
            self.assertEqual(pos[0].notional, 1450.0)
        finally:
            os.remove(path)

    def test_malformed_entry_fails_loudly_not_silently(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"positions": [{"symbol": "F", "kind": "equity"}]}, f)  # missing quantity/notional
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_positions(path)
        finally:
            os.remove(path)


class TestCLIEnforcesExistingPositions(unittest.TestCase):
    """Regression test for the gap: size_equity/size_long_option/size_csp were
    unit-tested with a `positions` argument, but main() never passed one, so
    MAX_SYMBOL_EXP and MAX_CONCURRENT were unenforceable through the actual
    `py engine/risk_engine.py ...` interface CLAUDE.md tells the agent to use.
    These tests invoke the real CLI as a subprocess, not the Python function."""

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, ENGINE_PATH, *args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _positions_file(self, positions):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"positions": positions}, f)
        f.close()
        return f.name

    def test_cli_trims_to_remaining_symbol_room(self):
        path = self._positions_file([
            {"symbol": "F", "kind": "equity", "quantity": 190, "notional": 2_800.0},  # 28% of 10k
        ])
        try:
            out = self._run("size-equity", "--account", "10000", "--entry", "14.50",
                             "--stop", "13.60", "--symbol", "F", "--positions-file", path)
        finally:
            os.remove(path)
        self.assertTrue(out["ok"])
        self.assertEqual(out["binding_constraint"], "MAX_SYMBOL_EXP")
        self.assertEqual(out["quantity"], 13.0)          # 13.79 floored to whole shares
        self.assertLessEqual(out["notional"], 200.0 + 1e-9)

    def test_cli_blocks_sixth_concurrent_position(self):
        path = self._positions_file(
            [{"symbol": f"S{i}", "kind": "equity", "quantity": 1, "notional": 100.0} for i in range(5)]
        )
        try:
            out = self._run("size-equity", "--account", "100000", "--entry", "50",
                             "--stop", "45", "--symbol", "NEW", "--positions-file", path)
        finally:
            os.remove(path)
        self.assertFalse(out["ok"])
        self.assertTrue(any("MAX_CONCURRENT" in r for r in out["reasons"]))

    def test_cli_with_no_positions_file_behaves_as_flat_account(self):
        out = self._run("size-equity", "--account", "10000", "--entry", "14.50",
                         "--stop", "13.60", "--symbol", "F",
                         "--positions-file", "no/such/file.json")
        self.assertTrue(out["ok"])
        self.assertEqual(out["binding_constraint"], "MAX_POS_NOTIONAL")


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
