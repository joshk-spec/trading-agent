"""Consistency tests between the documents and the engine.

The failure mode this exists to prevent: someone edits a number in CLAUDE.md and
the engine keeps enforcing the old one, or vice versa. Prose cannot be executed,
so the only way to keep 1,200 lines of markdown honest is to assert against it.

Also carries regression guards for all 18 contradictions found in the 2026-08-19
audit, so none of them can quietly return.

    python3 engine/test_doc_consistency.py
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import risk_engine as E  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


CLAUDE = read("CLAUDE.md")
README = read("README.md")
P1 = read("playbooks/P1_equity_momentum.md")
TRADE = read(".claude/commands/trade.md")
ALL_DOCS = {"CLAUDE.md": CLAUDE, "README.md": README, "P1": P1, "trade.md": TRADE}

# P2/P3/P4 were retired to the `retired-playbooks` branch on 2026-08-21. The
# guards that used to pin their internal consistency went with them — they
# cannot fail on documents that do not exist, and keeping them would have meant
# keeping the files purely to satisfy their own tests. What replaces them is
# TestRetiredPlaybooksStayRetired below, which pins the property that actually
# matters now: that they are gone and not referenced as live.
RETIRED_PLAYBOOKS = ["P2_swing_options.md", "P3_wheel.md", "P4_0dte.md"]


class TestConstantsMatchDocuments(unittest.TestCase):
    def test_sizing_block_matches_engine(self):
        """The §2.1 code block must literally state the engine's values."""
        pairs = [
            ("MAX_RISK_TRADE", E.MAX_RISK_TRADE_PCT),
            ("MAX_POS_NOTIONAL", E.MAX_POS_NOTIONAL_PCT),
            ("MAX_SYMBOL_EXP", E.MAX_SYMBOL_EXP_PCT),
            ("MAX_OPTIONS_EXP", E.MAX_OPTIONS_EXP_PCT),
        ]
        for name, value in pairs:
            with self.subTest(constant=name):
                m = re.search(rf"{name}\s*=\s*([0-9.]+)\s*\*\s*ACCOUNT", CLAUDE)
                self.assertIsNotNone(m, f"{name} not found in CLAUDE.md")
                self.assertAlmostEqual(float(m.group(1)), value, places=6)

    def test_max_concurrent_matches(self):
        m = re.search(r"MAX_CONCURRENT\s*=\s*(\d+)", CLAUDE)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), E.MAX_CONCURRENT)

    def test_drawdown_halts_match(self):
        d = re.search(r"DAILY_HALT\s*=\s*-([0-9.]+)\s*\*", CLAUDE)
        w = re.search(r"WEEKLY_HALT\s*=\s*-([0-9.]+)\s*\*", CLAUDE)
        self.assertAlmostEqual(float(d.group(1)), E.DAILY_HALT_PCT, places=6)
        self.assertAlmostEqual(float(w.group(1)), E.WEEKLY_HALT_PCT, places=6)

    def test_liquidity_gates_match(self):
        self.assertRegex(CLAUDE, rf"open_interest\s*>=\s*{E.MIN_OPEN_INTEREST}")
        self.assertRegex(CLAUDE, rf"volume\s*>=\s*{E.MIN_VOLUME}")
        self.assertRegex(CLAUDE, rf"<=\s*{E.MAX_SPREAD_PCT}")
        self.assertRegex(CLAUDE, rf">=\s*{E.ASK_SIZE_MULTIPLE}\s*\*\s*intended_contracts")

    def test_pdt_numbers_match(self):
        # \s+ because the phrase wraps a line in §2.4 — this used to be matched
        # against P4, which has been retired.
        self.assertRegex(CLAUDE, rf"{E.PDT_LIMIT} day trades per rolling\s+"
                                 rf"{E.PDT_WINDOW_DAYS} business days")
        self.assertIn("$25,000", CLAUDE)
        self.assertEqual(E.PDT_EXEMPT_ABOVE, 25_000.0)


class TestTierTablesAgree(unittest.TestCase):
    def _parse_tiers(self, doc):
        found = {}
        for m in re.finditer(r"\|\s*\*{0,2}(T[0-4])\*{0,2}\s*\|\s*([^|]+)\|", doc):
            found[m.group(1)] = m.group(2).strip()
        return found

    def test_claude_and_readme_tier_tables_identical(self):
        a, b = self._parse_tiers(CLAUDE), self._parse_tiers(README)
        self.assertEqual(set(a), {"T0", "T1", "T2", "T3", "T4"})
        for tier in a:
            with self.subTest(tier=tier):
                self.assertEqual(a[tier], b.get(tier),
                                 f"{tier} band differs between CLAUDE.md and README")

    def test_tier_bands_match_engine_bounds(self):
        bands = self._parse_tiers(CLAUDE)
        expected = {
            "T0": "< $700", "T1": "$700 – $2,500", "T2": "$2,500 – $10,000",
            "T3": "$10,000 – $25,000", "T4": "≥ $25,000",
        }
        self.assertEqual(bands, expected)
        # and those strings must reflect TIER_BOUNDS
        nums = [b[1] for b in E.TIER_BOUNDS[1:]]
        self.assertEqual(nums, [700.0, 2_500.0, 10_000.0, 25_000.0])

    def test_playbook_tier_claims_match_engine_gating(self):
        claims = {"P1": 0.0, "P2": 700.0, "P3": 10_000.0, "P4": 25_000.0}
        for pb, floor in claims.items():
            with self.subTest(playbook=pb):
                if floor > 0:
                    self.assertFalse(E.playbook_allowed(floor - 0.01, pb),
                                     f"{pb} should be locked below ${floor:,.0f}")
                self.assertTrue(E.playbook_allowed(floor, pb),
                                f"{pb} should unlock at ${floor:,.0f}")


class TestRegressionGuards(unittest.TestCase):
    """Each of these strings represents a contradiction fixed in the 2026-08-19
    audit. If one reappears, the corresponding bug is back."""

    def test_f2_symbol_exposure_aggregation_is_documented(self):
        self.assertIn("symbol_exposure", CLAUDE)
        self.assertIn("shares and options together", CLAUDE)

    def test_f3_engine_is_referenced_everywhere_sizing_happens(self):
        for name in ("CLAUDE.md", "P1", "trade.md"):
            with self.subTest(doc=name):
                self.assertIn("risk_engine.py", ALL_DOCS[name])

    def test_f4_no_dangling_short_branch_in_p1(self):
        self.assertNotIn("(short — see note)", P1)
        self.assertIn("P1 is long-only", P1)

    def test_f5_daily_halt_does_not_claim_auto_resume_of_operator_file(self):
        self.assertNotIn("Trading resumes next session.", CLAUDE)
        self.assertIn("HALT_TODAY", CLAUDE)
        self.assertIn("HALT_TODAY", TRADE)

    def test_f6_true_p1_risk_ceiling_stated(self):
        self.assertIn("3.0%", CLAUDE + P1)
        self.assertRegex(P1, r"unreachable|cannot reach it")

    def test_f10_redundant_abs_spread_gate_removed(self):
        self.assertNotRegex(CLAUDE, r"abs_spread\s*<=\s*0\.10\s*#")

    def test_f11_fractional_share_limit_is_stated_in_p1(self):
        self.assertIn("100 whole shares", P1)

    def test_f13_max_concurrent_enforced_in_execution_sequence(self):
        self.assertIn("MAX_CONCURRENT", CLAUDE)
        self.assertIn("fewer than 5 positions open", CLAUDE)

    def test_f14_no_broken_section_reference(self):
        self.assertNotIn("(§3.3)", CLAUDE)

    def test_f15_pdt_report_line_handles_t4(self):
        self.assertIn("above $25k", CLAUDE)

    def test_f16_mid_session_tier_crossing_defined(self):
        self.assertIn("re-evaluated before every order", CLAUDE)

    def test_f17_journal_reports_realized_not_target_risk(self):
        self.assertIn("NOT the 5% target", CLAUDE)
        self.assertNotIn("computed: MAX_RISK_TRADE $X / unit risk $Y", CLAUDE)

    def test_f19_p1_stop_is_intraday_not_close_based(self):
        """A 15-year backtest showed the close-based reading and the resting
        stop-limit in §6 step 9 are different exits with materially different
        win rates. Only one may be in force, and it is the broker order's."""
        self.assertNotIn("Stop hit (close below `stop_price`)", P1)
        self.assertIn("Stop touched intraday", P1)
        self.assertIn("INTRADAY touch, not a close", P1)

    def test_f20_p1_names_exactly_one_target_rule(self):
        """The old menu — 'prior high, measured move, or a resistance level' —
        left P1 UNEXECUTABLE: read as a prior high, 0 of 341 otherwise-valid
        candidates in 15 years cleared the 2.0 reward:risk minimum."""
        self.assertNotIn("prior high, measured move, or a resistance level", P1)
        self.assertIn("swing_high + (swing_high - pullback_low)", P1)

    def test_f21_the_unexecutable_target_reading_stays_documented(self):
        """Keep the reason pinned. Without it someone 'simplifies' the target
        rule back to a prior high and silently disables the playbook again."""
        self.assertIn("unexecutable", P1)
        self.assertIn("research/FINDINGS.md", P1)


class TestStructuralIntegrity(unittest.TestCase):
    def test_every_referenced_playbook_file_exists(self):
        for rel in re.findall(r"playbooks/[A-Za-z0-9_]+\.md", CLAUDE):
            with self.subTest(path=rel):
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), f"missing {rel}")

    def test_engine_paths_in_docs_resolve(self):
        for rel in sorted(set(re.findall(r"engine/[A-Za-z0-9_]+\.py", CLAUDE + README + TRADE))):
            with self.subTest(path=rel):
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), f"missing {rel}")

    def test_docs_point_at_the_full_test_runner(self):
        """The agent must run both suites, not just the engine ones."""
        for name in ("CLAUDE.md", "trade.md", "README.md"):
            with self.subTest(doc=name):
                self.assertIn("run_all_tests.py", ALL_DOCS[name])

    def test_stated_test_count_matches_reality(self):
        """A stale count in the docs is exactly the drift this suite exists for."""
        import test_risk_engine as TRE
        loader = unittest.TestLoader()
        total = (loader.loadTestsFromModule(TRE).countTestCases()
                 + loader.loadTestsFromModule(sys.modules[__name__]).countTestCases())
        for name in ("trade.md", "README.md"):
            claimed = re.search(r"(\d+) tests", ALL_DOCS[name])
            if claimed:
                with self.subTest(doc=name):
                    self.assertEqual(int(claimed.group(1)), total,
                                     f"{name} claims {claimed.group(1)}, actual {total}")

    def test_per_module_test_counts_in_readme_match_reality(self):
        """The totals guard only checks the FIRST '<n> tests' in each doc, so the
        per-file counts in README's Structure block drifted unnoticed (it claimed
        32 unit tests when there were 65). Pin them individually."""
        import test_risk_engine as TRE
        loader = unittest.TestLoader()
        actual = {
            "test_risk_engine.py": loader.loadTestsFromModule(TRE).countTestCases(),
            "test_doc_consistency.py": loader.loadTestsFromModule(
                sys.modules[__name__]).countTestCases(),
        }
        for filename, count in actual.items():
            with self.subTest(module=filename):
                m = re.search(rf"{re.escape(filename)}\s+(\d+)\s+(?:unit\s+)?tests", README)
                self.assertIsNotNone(m, f"README does not state a test count for {filename}")
                self.assertEqual(int(m.group(1)), count,
                                 f"README claims {m.group(1)} for {filename}, actual {count}")

    def test_readme_does_not_claim_the_account_is_unfunded(self):
        """The account was funded on 2026-08-20. A README that still says $0 /
        unfunded misleads about whether real money is at stake."""
        self.assertNotRegex(README, r"Account value is \*\*\$0\*\*")
        self.assertNotIn("unfunded", README)

    def test_fractional_stop_gap_is_documented_where_it_bites(self):
        """stop_eligible: false means no broker-side stop and no intraday
        protection. That must be stated in the constitution, the playbook that
        produces fractional positions, and the operator-facing README."""
        for name in ("CLAUDE.md", "P1", "README.md"):
            with self.subTest(doc=name):
                self.assertIn("stop_eligible", ALL_DOCS[name])

    def test_engine_invocations_use_one_consistent_interpreter(self):
        """Mixed `python` / `python3` / `py` across docs means half the commands
        fail on any given machine. Pin them to one."""
        found = set()
        for name, doc in ALL_DOCS.items():
            for m in re.finditer(r"\b(python3?|py)\s+engine/", doc):
                found.add(m.group(1))
        self.assertLessEqual(len(found), 1, f"mixed interpreters in docs: {found}")

    def test_engine_invocations_use_forward_slashes(self):
        for name, doc in ALL_DOCS.items():
            with self.subTest(doc=name):
                self.assertNotRegex(doc, r"\bpy\s+engine\\",
                                    "use engine/ not engine\\ so paths work everywhere")

    def test_no_section_reference_points_past_the_last_section(self):
        defined = {int(m) for m in re.findall(r"^## §(\d+)\.", CLAUDE, re.M)}
        cited = {int(m) for m in re.findall(r"§(\d+)", CLAUDE + P1 + TRADE)}
        self.assertTrue(cited <= defined, f"dangling refs: {sorted(cited - defined)}")

    def test_single_leg_only_constraint_is_stated(self):
        self.assertIn("SINGLE-LEG ONLY", CLAUDE)
        self.assertIn("No spreads", CLAUDE)

    def test_account_number_consistent_everywhere(self):
        accounts = set(re.findall(r"\b79397360\d\b", CLAUDE + README + TRADE))
        self.assertEqual(accounts, {"793973603"}, f"conflicting account numbers: {accounts}")


class TestRetiredPlaybooksStayRetired(unittest.TestCase):
    """P2/P3/P4 were retired on 2026-08-21: unreachable below $700/$10k/$25k,
    never backtested, and P3/P4 not backtestable by an equity-bar harness. They
    carried roughly half the [HARD] rules in the repo while contributing nothing
    at any balance held. They live on the `retired-playbooks` branch."""

    def test_retired_playbook_files_are_absent(self):
        for name in RETIRED_PLAYBOOKS:
            with self.subTest(playbook=name):
                self.assertFalse(
                    os.path.exists(os.path.join(ROOT, "playbooks", name)),
                    f"{name} is back on main; retire it or re-validate it")

    def test_no_live_document_points_at_a_retired_playbook_file(self):
        """A dangling path is worse than a missing rule: the agent is told to
        read the playbook during a run and would find nothing."""
        for doc, text in ALL_DOCS.items():
            for name in RETIRED_PLAYBOOKS:
                with self.subTest(doc=doc, playbook=name):
                    self.assertNotIn(f"playbooks/{name}", text)

    def test_constitution_records_that_a_missing_playbook_means_no(self):
        self.assertIn("A playbook with no file in", CLAUDE)
        self.assertIn("retired-playbooks", CLAUDE)

    def test_the_duplicate_local_runner_is_gone(self):
        """run_trade.ps1 drove a second agent against the same account and the
        same day-trade counter."""
        self.assertFalse(os.path.exists(os.path.join(ROOT, "run_trade.ps1")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
