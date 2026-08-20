"""
risk_engine.py — deterministic money math for the trading constitution.

THE POINT OF THIS FILE
The agent must never compute position size, tier, exposure, drawdown, or day-trade
counts by reasoning. Every number that decides how much money is at stake comes
from here, where it is unit-tested once instead of re-derived under time pressure
every session.

If a number in CLAUDE.md disagrees with a number in this file, THIS FILE WINS and
the discrepancy is a §7 incident.

Usage from the agent:
    python3 engine/risk_engine.py size-equity --account 5000 --entry 14.50 --stop 13.60
    python3 engine/risk_engine.py size-option --account 5000 --premium 1.40
    python3 engine/risk_engine.py preflight --account 5000 --session-open 5200 --week-open 5400

size-equity, size-option, and size-csp read state/positions.json by default
(override with --positions-file) to enforce MAX_SYMBOL_EXP and MAX_CONCURRENT
against what's actually open. That file must be kept current every session —
a stale one under-counts exposure without any error.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Literal, Sequence

# ─────────────────────────── CONSTITUTIONAL CONSTANTS ───────────────────────────
# These mirror CLAUDE.md §2.1. Changing one here without changing the document
# (or vice versa) is a bug. The test suite pins every one of them.

MAX_RISK_TRADE_PCT   = 0.05   # 5% of account risked per trade
MAX_RISK_TRADE_P4    = 0.02   # 2% for 0DTE — gamma slippage makes stops unreliable
MAX_POS_NOTIONAL_PCT = 0.25   # 25% of account in any one position
MAX_SYMBOL_EXP_PCT   = 0.30   # 30% of account in any one underlying, ALL instruments
MAX_OPTIONS_EXP_PCT  = 0.40   # 40% of account in options exposure, INCLUDING CSP collateral
MAX_CONCURRENT       = 5      # open positions

DAILY_HALT_PCT       = 0.10   # -10% vs session open
WEEKLY_HALT_PCT      = 0.20   # -20% vs week open
MIN_ACCOUNT_VALUE    = 50.0   # below this nothing is executable (§7)

P1_MAX_STOP_PCT      = 0.12   # P1 rejects stops wider than 12% of entry
P1_MIN_RR            = 2.0    # P1 minimum reward:risk at entry
CSP_MAX_COLLATERAL_PCT = 0.25 # single CSP collateral ceiling

# Robinhood accepts fractional share quantities to 6 decimal places.
SHARE_DECIMALS       = 6

PDT_LIMIT            = 3      # day trades per rolling 5 business days
PDT_WINDOW_DAYS      = 5      # business days
PDT_EXEMPT_ABOVE     = 25_000.0

TIER_BOUNDS = [
    ("T0",      0.0,    700.0,  ("P1",)),
    ("T1",    700.0,  2_500.0,  ("P1", "P2")),
    ("T2",  2_500.0, 10_000.0,  ("P1", "P2")),
    ("T3", 10_000.0, 25_000.0,  ("P1", "P2", "P3")),
    ("T4", 25_000.0, math.inf,  ("P1", "P2", "P3", "P4")),
]
T1_MAX_CONTRACT_PCT = 0.20    # at T1 only, one contract may not exceed 20% of account

# Option liquidity gates (§2.5)
MIN_OPEN_INTEREST    = 1000
MIN_VOLUME           = 100
MAX_SPREAD_PCT       = 0.05
ASK_SIZE_MULTIPLE    = 10     # ask_size must be >= this * intended contracts

Kind = Literal["equity", "long_option", "short_put", "short_call"]
VALID_KINDS = ("equity", "long_option", "short_put", "short_call")

DEFAULT_POSITIONS_FILE = "state/positions.json"


# ────────────────────────────────── MODELS ──────────────────────────────────
@dataclass(frozen=True)
class Position:
    """One open position. `notional` is dollars of exposure attributable to this
    position: shares*price for equity, premium*100*qty for long options,
    strike*100*qty (collateral) for short puts, shares_covered*price for covered calls."""
    symbol: str
    kind: Kind
    quantity: float
    notional: float

    @property
    def is_option(self) -> bool:
        return self.kind in ("long_option", "short_put", "short_call")


def load_positions(path: str = DEFAULT_POSITIONS_FILE) -> list[Position]:
    """Load current open positions from a state file (state/positions.json's
    `positions` array) for MAX_SYMBOL_EXP / MAX_CONCURRENT checks.

    This is the fix for a real gap: size_equity/size_long_option/size_csp all
    accept a `positions` argument and are unit-tested against it, but the CLI
    previously never passed one — meaning MAX_SYMBOL_EXP and MAX_CONCURRENT
    were structurally unenforceable through the only interface the agent is
    told to use ("shell out to it"). No file yet ⇒ no open positions, not an
    error. A file that exists but is malformed fails loudly — under-counting
    exposure silently is worse than crashing."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(
            f"{path} is not valid JSON ({e}). Fix state/positions.json before sizing — "
            f"a bad file must not silently under-count exposure."
        ) from e
    positions: list[Position] = []
    for i, p in enumerate(data.get("positions", [])):
        try:
            kind = p["kind"]
            if kind not in VALID_KINDS:
                raise ValueError(f"kind {kind!r} not one of {VALID_KINDS}")
            positions.append(Position(
                symbol=str(p["symbol"]),
                kind=kind,
                quantity=float(p["quantity"]),
                notional=float(p["notional"]),
            ))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(
                f"positions[{i}] in {path} is malformed ({e}). Fix state/positions.json "
                f"before sizing — a bad entry must not silently under-count exposure."
            ) from e
    return positions


@dataclass
class SizeResult:
    ok: bool
    quantity: float = 0.0
    notional: float = 0.0
    risk_dollars: float = 0.0
    risk_pct: float = 0.0
    binding_constraint: str = ""
    reasons: list[str] = field(default_factory=list)
    # True when the quantity is a whole number of shares, i.e. a broker-side
    # protective stop (§6 step 9) CAN be placed. Robinhood rejects stop orders
    # on fractional quantities, so a False here means the position will have no
    # intraday protection between sessions and the journal must say so.
    # Always True for option contracts, which are indivisible by construction.
    stop_eligible: bool = True

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ─────────────────────────────────── TIERS ───────────────────────────────────
def resolve_tier(account_value: float) -> str:
    if account_value < 0:
        raise ValueError("account_value cannot be negative")
    for name, lo, hi, _ in TIER_BOUNDS:
        if lo <= account_value < hi:
            return name
    return "T4"


def playbooks_for(account_value: float) -> tuple[str, ...]:
    tier = resolve_tier(account_value)
    for name, _, _, pbs in TIER_BOUNDS:
        if name == tier:
            return pbs
    return ()


def playbook_allowed(account_value: float, playbook: str) -> bool:
    return playbook.upper() in playbooks_for(account_value)


def max_risk_trade(account_value: float, playbook: str = "P1") -> float:
    pct = MAX_RISK_TRADE_P4 if playbook.upper() == "P4" else MAX_RISK_TRADE_PCT
    return account_value * pct


# ──────────────────────────────── EXPOSURE ────────────────────────────────
def symbol_exposure(positions: Sequence[Position], symbol: str) -> float:
    """Total dollar exposure to one underlying across EVERY instrument type.
    This is the aggregation CLAUDE.md §2.1 requires and no playbook computed."""
    return sum(p.notional for p in positions if p.symbol.upper() == symbol.upper())


def options_exposure(positions: Sequence[Position]) -> float:
    """All options exposure including short-put collateral. CSP collateral counts
    here — that is why P3's separate aggregate cap was removed."""
    return sum(p.notional for p in positions if p.is_option)


def check_caps(
    account_value: float,
    positions: Sequence[Position],
    symbol: str,
    add_notional: float,
    is_option: bool,
    opening_new_position: bool = True,
) -> list[str]:
    """Every portfolio-level cap, evaluated against the position being added.
    Returns a list of violations; empty means clear."""
    v: list[str] = []

    if add_notional > account_value * MAX_POS_NOTIONAL_PCT + 1e-9:
        v.append(
            f"MAX_POS_NOTIONAL: ${add_notional:,.2f} > "
            f"${account_value * MAX_POS_NOTIONAL_PCT:,.2f} (25% of account)"
        )

    sym_after = symbol_exposure(positions, symbol) + add_notional
    if sym_after > account_value * MAX_SYMBOL_EXP_PCT + 1e-9:
        v.append(
            f"MAX_SYMBOL_EXP: {symbol} exposure would be ${sym_after:,.2f} > "
            f"${account_value * MAX_SYMBOL_EXP_PCT:,.2f} (30% of account). "
            f"Existing ${symbol_exposure(positions, symbol):,.2f} + new ${add_notional:,.2f}"
        )

    if is_option:
        opt_after = options_exposure(positions) + add_notional
        if opt_after > account_value * MAX_OPTIONS_EXP_PCT + 1e-9:
            v.append(
                f"MAX_OPTIONS_EXP: options exposure would be ${opt_after:,.2f} > "
                f"${account_value * MAX_OPTIONS_EXP_PCT:,.2f} (40% of account)"
            )

    if opening_new_position and len(positions) >= MAX_CONCURRENT:
        v.append(f"MAX_CONCURRENT: already {len(positions)} open, limit {MAX_CONCURRENT}")

    return v


# ──────────────────────────────── SIZING ────────────────────────────────
def size_equity(
    account_value: float,
    entry: float,
    stop: float,
    symbol: str = "",
    positions: Sequence[Position] = (),
    target: float = 0.0,
) -> SizeResult:
    """P1 equity sizing. Fractional shares permitted, so the risk target is
    reachable — but MAX_POS_NOTIONAL almost always binds first, which means
    realized risk lands well under 5%. That is intended; report the realized number.

    `target`, when supplied, is checked against P1's [HARD] minimum reward:risk
    of 2.0 so that rule is enforced by code rather than by the agent's arithmetic.
    Left at 0.0 the check is skipped, for callers sizing something other than a
    fresh P1 entry."""
    r = SizeResult(ok=False)

    if entry <= 0 or stop <= 0:
        r.reasons.append("entry and stop must be positive")
        return r
    if stop >= entry:
        r.reasons.append(f"stop ${stop:.2f} must be below entry ${entry:.2f} (long only)")
        return r
    if account_value < MIN_ACCOUNT_VALUE:
        r.reasons.append(f"account ${account_value:,.2f} below ${MIN_ACCOUNT_VALUE:,.2f} floor (§7)")
        return r

    risk_per_share = entry - stop
    stop_pct = risk_per_share / entry
    if stop_pct > P1_MAX_STOP_PCT + 1e-9:
        r.reasons.append(
            f"stop is {stop_pct:.2%} of entry, P1 rejects wider than {P1_MAX_STOP_PCT:.0%} — too volatile"
        )
        return r

    if target:
        if target <= entry:
            r.reasons.append(
                f"target ${target:.2f} must be above entry ${entry:.2f} (long only)"
            )
            return r
        rr = (target - entry) / risk_per_share
        if rr < P1_MIN_RR - 1e-9:
            r.reasons.append(
                f"reward:risk {rr:.2f} < {P1_MIN_RR:.1f} minimum "
                f"(entry ${entry:.2f}, stop ${stop:.2f}, target ${target:.2f}). "
                f"Find a better entry or a real structural target — do not move the stop."
            )
            return r

    budget = max_risk_trade(account_value, "P1")
    shares = budget / risk_per_share
    notional = shares * entry
    binding = "MAX_RISK_TRADE"

    cap = account_value * MAX_POS_NOTIONAL_PCT
    if notional > cap:
        shares = cap / entry
        notional = cap
        binding = "MAX_POS_NOTIONAL"

    # symbol cap can bind tighter still
    if symbol:
        room = account_value * MAX_SYMBOL_EXP_PCT - symbol_exposure(positions, symbol)
        if room <= 0:
            r.reasons.append(f"MAX_SYMBOL_EXP: no room left in {symbol}")
            return r
        if notional > room:
            shares = room / entry
            notional = room
            binding = "MAX_SYMBOL_EXP"

    violations = check_caps(account_value, positions, symbol or "?", notional, is_option=False)
    # notional/symbol already trimmed above; only concurrency can still fail
    violations = [x for x in violations if x.startswith("MAX_CONCURRENT")]
    if violations:
        r.reasons.extend(violations)
        return r

    # FLOOR, never round, to the broker's fractional precision. round() can go
    # UP, which would push notional and risk back above the cap that was just
    # enforced — a cap that binds must not be undone by presentation rounding.
    scale = 10 ** SHARE_DECIMALS
    shares = math.floor(shares * scale) / scale
    if shares <= 0:
        r.reasons.append(
            f"sized quantity rounds to zero shares at {SHARE_DECIMALS}dp "
            f"(entry ${entry:,.2f} vs available room) — skip"
        )
        return r

    # Recompute from the quantity actually orderable, not the pre-floor ideal.
    notional = shares * entry
    risk_dollars = shares * risk_per_share
    return SizeResult(
        ok=True,
        quantity=shares,
        notional=round(notional, 2),
        risk_dollars=round(risk_dollars, 2),
        risk_pct=risk_dollars / account_value,
        binding_constraint=binding,
        stop_eligible=float(shares).is_integer(),
    )


def size_long_option(
    account_value: float,
    premium: float,
    symbol: str = "",
    positions: Sequence[Position] = (),
    playbook: str = "P2",
) -> SizeResult:
    """P2/P4 long option sizing. Contracts are INDIVISIBLE — this is the Minimum
    Viable Unit rule (§2.3) and the reason small accounts cannot trade options.
    Sized against a 100% loss of premium, deliberately: the -50% stop is not
    guaranteed reachable through a gap."""
    r = SizeResult(ok=False)

    if premium <= 0:
        r.reasons.append("premium must be positive")
        return r
    if not playbook_allowed(account_value, playbook):
        r.reasons.append(
            f"{playbook} not unlocked at {resolve_tier(account_value)} "
            f"(account ${account_value:,.2f})"
        )
        return r

    cost_per_contract = premium * 100.0
    budget = max_risk_trade(account_value, playbook)
    contracts = math.floor(budget / cost_per_contract)

    if contracts < 1:
        r.reasons.append(
            f"MINIMUM VIABLE UNIT: 1 contract costs ${cost_per_contract:,.2f}, "
            f"risk budget is ${budget:,.2f}. floor({budget:.2f}/{cost_per_contract:.2f}) = 0. "
            f"SKIP — do not round up (§2.3)."
        )
        return r

    # T1 only: a single contract may not exceed 20% of the account
    if resolve_tier(account_value) == "T1":
        t1_cap = account_value * T1_MAX_CONTRACT_PCT
        if cost_per_contract > t1_cap:
            r.reasons.append(
                f"T1 rule: one contract ${cost_per_contract:,.2f} > "
                f"${t1_cap:,.2f} (20% of account)"
            )
            return r

    notional = contracts * cost_per_contract
    violations = check_caps(account_value, positions, symbol or "?", notional, is_option=True)
    if violations:
        # try trimming contracts to fit
        while contracts > 1:
            contracts -= 1
            notional = contracts * cost_per_contract
            violations = check_caps(account_value, positions, symbol or "?", notional, is_option=True)
            if not violations:
                break
        if violations:
            r.reasons.extend(violations)
            return r

    return SizeResult(
        ok=True,
        quantity=contracts,
        notional=round(notional, 2),
        risk_dollars=round(notional, 2),   # max loss on a long option IS the premium
        risk_pct=notional / account_value,
        binding_constraint="MAX_RISK_TRADE (indivisible contract)",
    )


def size_csp(
    account_value: float,
    cash_available: float,
    strike: float,
    symbol: str = "",
    positions: Sequence[Position] = (),
) -> SizeResult:
    """P3 cash-secured put. Collateral is strike*100 per contract and counts toward
    MAX_OPTIONS_EXP — there is no separate, looser aggregate CSP ceiling."""
    r = SizeResult(ok=False)

    if strike <= 0:
        r.reasons.append("strike must be positive")
        return r
    if not playbook_allowed(account_value, "P3"):
        r.reasons.append(f"P3 not unlocked at {resolve_tier(account_value)}")
        return r

    collateral_per = strike * 100.0
    single_cap = account_value * CSP_MAX_COLLATERAL_PCT
    if collateral_per > single_cap:
        r.reasons.append(
            f"CSP collateral ${collateral_per:,.2f} for one contract > "
            f"${single_cap:,.2f} (25% of account). Underlying too expensive for this account."
        )
        return r

    contracts = math.floor(single_cap / collateral_per)
    while contracts >= 1:
        notional = contracts * collateral_per
        violations = check_caps(account_value, positions, symbol or "?", notional, is_option=True)
        if notional > cash_available + 1e-9:
            violations.append(
                f"CASH: collateral ${notional:,.2f} exceeds cash on hand ${cash_available:,.2f}"
            )
        if not violations:
            return SizeResult(
                ok=True,
                quantity=contracts,
                notional=round(notional, 2),
                risk_dollars=round(notional, 2),
                risk_pct=notional / account_value,
                binding_constraint="CSP_MAX_COLLATERAL / MAX_OPTIONS_EXP",
            )
        contracts -= 1

    r.reasons.append("no contract count satisfies all caps and cash on hand")
    return r


# ──────────────────────────── PDT / DAY TRADES ────────────────────────────
def _business_days_back(anchor: date, n: int) -> date:
    """First business day of an n-business-day window ending on `anchor`."""
    seen, d = 1, anchor
    while seen < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            seen += 1
    return d


def count_day_trades(log: Sequence[dict], today: date | None = None) -> int:
    """Day trades inside the rolling 5-business-day window ending today.
    `log` entries need a 'date' key of YYYY-MM-DD."""
    today = today or date.today()
    window_start = _business_days_back(today, PDT_WINDOW_DAYS)
    n = 0
    for e in log:
        d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        if window_start <= d <= today:
            n += 1
    return n


def day_trades_available(account_value: float, log: Sequence[dict], today: date | None = None) -> int:
    """How many day trades remain. Unlimited (represented as 999) at/above $25k."""
    if account_value >= PDT_EXEMPT_ABOVE:
        return 999
    return max(0, PDT_LIMIT - count_day_trades(log, today))


# ───────────────────────────────── DRAWDOWN ─────────────────────────────────
@dataclass
class HaltDecision:
    halt: bool
    reasons: list[str] = field(default_factory=list)
    daily_pct: float = 0.0
    weekly_pct: float = 0.0
    # Halt checks that could NOT be evaluated because their mark was missing or
    # non-positive. A halt=False carrying entries here does not mean "no
    # drawdown breach" — it means the question was never asked. §2.0 forbids
    # trading on a [HARD] rule you cannot verify, so a non-empty list must be
    # treated as blocking, not as an all-clear.
    checks_skipped: list[str] = field(default_factory=list)


def check_drawdown(account_value: float, session_open: float, week_open: float) -> HaltDecision:
    d = HaltDecision(halt=False)

    if not (session_open and session_open > 0):
        d.checks_skipped.append(
            "DAILY_HALT not evaluated: session-open mark missing or non-positive. "
            "Populate state/marks.json before trading (§3 step 5)."
        )
    if not (week_open and week_open > 0):
        d.checks_skipped.append(
            "WEEKLY_HALT not evaluated: week-open mark missing or non-positive. "
            "Populate state/marks.json before trading (§3 step 5)."
        )

    if session_open and session_open > 0:
        d.daily_pct = (account_value - session_open) / session_open
        if d.daily_pct <= -DAILY_HALT_PCT:
            d.halt = True
            d.reasons.append(
                f"DAILY_HALT breached: {d.daily_pct:.2%} vs limit -{DAILY_HALT_PCT:.0%} "
                f"(${session_open:,.2f} → ${account_value:,.2f})"
            )

    if week_open and week_open > 0:
        d.weekly_pct = (account_value - week_open) / week_open
        if d.weekly_pct <= -WEEKLY_HALT_PCT:
            d.halt = True
            d.reasons.append(
                f"WEEKLY_HALT breached: {d.weekly_pct:.2%} vs limit -{WEEKLY_HALT_PCT:.0%} "
                f"(${week_open:,.2f} → ${account_value:,.2f}). OPERATOR MUST CLEAR."
            )

    if account_value < MIN_ACCOUNT_VALUE:
        d.halt = True
        d.reasons.append(f"Account ${account_value:,.2f} below ${MIN_ACCOUNT_VALUE:,.2f} floor (§7)")

    return d


# ──────────────────────────── OPTION LIQUIDITY ────────────────────────────
def check_option_liquidity(
    open_interest: int, volume: int, bid: float, ask: float,
    mark: float, intended_contracts: int, ask_size: int,
) -> list[str]:
    """§2.5 gates. Returns violations; empty means clear."""
    v: list[str] = []
    if open_interest < MIN_OPEN_INTEREST:
        v.append(f"open_interest {open_interest} < {MIN_OPEN_INTEREST}")
    if volume < MIN_VOLUME:
        v.append(f"volume {volume} < {MIN_VOLUME}")
    if bid <= 0:
        v.append("bid is zero — contract is untradeable on exit")
    if mark <= 0:
        v.append("mark is zero")
    else:
        spread_pct = (ask - bid) / mark
        if spread_pct > MAX_SPREAD_PCT + 1e-9:
            v.append(f"spread {spread_pct:.2%} > {MAX_SPREAD_PCT:.0%} (bid {bid:.2f}/ask {ask:.2f})")
    need = ASK_SIZE_MULTIPLE * intended_contracts
    if ask_size < need:
        v.append(f"ask_size {ask_size} < {need} ({ASK_SIZE_MULTIPLE}x intended {intended_contracts})")
    return v


# ──────────────────────────────────── CLI ────────────────────────────────────
def _add_positions_file_arg(s: argparse.ArgumentParser) -> None:
    s.add_argument("--positions-file", default=DEFAULT_POSITIONS_FILE,
                    help="JSON file of currently open positions, for MAX_SYMBOL_EXP/MAX_CONCURRENT")


def main() -> None:
    p = argparse.ArgumentParser(description="Deterministic risk math. Never compute these by hand.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("size-equity"); s.add_argument("--account", type=float, required=True)
    s.add_argument("--entry", type=float, required=True); s.add_argument("--stop", type=float, required=True)
    s.add_argument("--symbol", default="")
    s.add_argument("--target", type=float, default=0.0,
                   help="Structural target. When given, enforces P1's 2.0 minimum reward:risk.")
    _add_positions_file_arg(s)

    s = sub.add_parser("size-option"); s.add_argument("--account", type=float, required=True)
    s.add_argument("--premium", type=float, required=True); s.add_argument("--symbol", default="")
    s.add_argument("--playbook", default="P2")
    _add_positions_file_arg(s)

    s = sub.add_parser("size-csp"); s.add_argument("--account", type=float, required=True)
    s.add_argument("--cash", type=float, required=True); s.add_argument("--strike", type=float, required=True)
    s.add_argument("--symbol", default="")
    _add_positions_file_arg(s)

    s = sub.add_parser("preflight"); s.add_argument("--account", type=float, required=True)
    s.add_argument("--session-open", type=float, default=0.0); s.add_argument("--week-open", type=float, default=0.0)

    a = p.parse_args()
    if a.cmd == "size-equity":
        positions = load_positions(a.positions_file)
        print(size_equity(a.account, a.entry, a.stop, a.symbol, positions, a.target).to_json())
    elif a.cmd == "size-option":
        positions = load_positions(a.positions_file)
        print(size_long_option(a.account, a.premium, a.symbol, positions, a.playbook).to_json())
    elif a.cmd == "size-csp":
        positions = load_positions(a.positions_file)
        print(size_csp(a.account, a.cash, a.strike, a.symbol, positions).to_json())
    elif a.cmd == "preflight":
        d = check_drawdown(a.account, a.session_open, a.week_open)
        print(json.dumps({
            "tier": resolve_tier(a.account),
            "playbooks": list(playbooks_for(a.account)),
            "max_risk_trade": round(max_risk_trade(a.account), 2),
            "pdt_applies": a.account < PDT_EXEMPT_ABOVE,
            "halt": d.halt, "reasons": d.reasons,
            "daily_pct": round(d.daily_pct, 4), "weekly_pct": round(d.weekly_pct, 4),
            "checks_skipped": d.checks_skipped,
        }, indent=2))


if __name__ == "__main__":
    main()
