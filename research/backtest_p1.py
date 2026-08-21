"""Backtest of playbook P1 (equity momentum / trend continuation).

WHAT THIS ANSWERS
  1. How often does P1 actually trigger? (the "why hasn't it traded" question)
  2. Does it have an edge? (win rate, average R, expectancy, drawdown)

THE RULE THAT GOVERNS THIS FILE: no future data may influence a decision.
A signal at bar T is computed from bars[0..T] only. The entry happens at T+1
and may only use T+1's open/low to determine the fill. Every indicator here is
causal by construction, and `test_backtest.py` asserts it by feeding the engine
a series whose future bars are replaced with garbage and checking the signals
are unchanged. Lookahead is the defect that makes a backtest lie, and it is
invisible in the output — the only defence is that test.

WHAT IS FAITHFUL TO THE PLAYBOOK
  Universe price >= $5 and 20-day average dollar volume >= $50M; trend
  structure (close > SMA50 > SMA200, SMA50 rising over 10 sessions, price
  within 8% of the trailing 252-day high); pullback of 3-10% off a 20-day swing
  high into/near the 20-EMA on declining volume; RSI(14) fell into 40-55 and
  turned up, never below 30; relative strength vs SPY over 20 sessions; market
  regime (SPY above its 50-SMA, longs suspended below its 200-SMA); the entry
  trigger (close above the prior session's high on volume >= the 20-day
  average); the 2% gap-void rule; the stop at min(pullback low, entry - 2*ATR14)
  with the 12%-of-entry rejection; the 2.0 minimum reward:risk; and the exit
  table (stop, breakeven trail at +1R, half off at +2R with a 1.5-ATR trail,
  two consecutive closes below the 20-EMA, and the 20-session time stop).

WHAT IS APPROXIMATED, AND WHY (these are the honest caveats)
  * "Structural target" is qualitative in the playbook. Here it is the highest
    high of the trailing 60 sessions — a real prior resistance level. When that
    level is at or below the entry there is no structural target, and the trade
    is skipped rather than inventing one by multiplying the stop.
  * Earnings exclusion is NOT modelled — historical earnings dates are not in
    the bar data. Live, P1 refuses names with earnings in the holding horizon,
    which removes some of the largest gap losses. This backtest therefore
    carries earnings risk the live strategy does not, biasing results DOWN.
  * Bid-ask spread, slippage and commissions are NOT modelled. On the liquid
    names here the spread gate is ~0.15%, so this biases results UP slightly.
  * Optionability and the halted/inactive-symbol check are not modelled.
  * MAX_CONCURRENT (5) and the exposure caps are NOT applied: this measures
    per-trade edge, which is size-independent. Portfolio caps reduce how many
    of these trades you could actually hold at once; they do not change the
    edge of the ones you do take.
  * The universe is survivorship-biased — every symbol still trades today.
    Names that were liquid and later collapsed or were delisted are absent,
    which flatters a long-only trend strategy. This is the single largest
    upward bias in the study and cannot be removed with this data source.

TWO STOP MODELS, because the documents disagree
  P1's exit table says "Stop hit (close below stop_price)" — a CLOSE-based
  stop. But CLAUDE.md §6 step 9 now rests a stop-LIMIT order at the broker,
  which triggers intraday on any touch. Those are different exits: a dip
  through the stop that closes back above it is a loss under one and a
  non-event under the other. Both are simulated and reported so the difference
  is measured rather than argued about.

    py research/backtest_p1.py
    py research/backtest_p1.py --stop-model close
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import statistics
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
BENCHMARK = "SPY"

# ---- Playbook constants (mirroring playbooks/P1_equity_momentum.md) ----
MIN_PRICE            = 5.00
MIN_ADV_DOLLARS      = 50_000_000
SMA_FAST, SMA_SLOW   = 50, 200
SMA_SLOPE_LOOKBACK   = 10
HIGH_52W_LOOKBACK    = 252
MAX_PCT_BELOW_HIGH   = 0.08
SWING_LOOKBACK       = 20
RETRACE_MIN, RETRACE_MAX = 0.03, 0.10
EMA_PERIOD           = 20
EMA_PROXIMITY        = 0.02      # pullback low must reach within 2% of the 20-EMA
RSI_PERIOD           = 14
RSI_BAND_LO, RSI_BAND_HI = 40.0, 55.0
RSI_FLOOR            = 30.0      # below this is a downtrend, not a pullback
RSI_WINDOW           = 10
RS_LOOKBACK          = 20
VOL_AVG_LOOKBACK     = 20
ATR_PERIOD           = 14
ATR_STOP_MULT        = 2.0
MAX_STOP_PCT         = 0.12
MIN_RR               = 2.0
TARGET_LOOKBACK      = 60
MAX_GAP_UP           = 0.02
TIME_STOP_SESSIONS   = 20
EMA_EXIT_CONSECUTIVE = 2
TRAIL_ATR_MULT       = 1.5


# ────────────────────────────── data ──────────────────────────────
@dataclass
class Series:
    symbol: str
    date: list[str] = field(default_factory=list)
    o: list[float] = field(default_factory=list)
    h: list[float] = field(default_factory=list)
    l: list[float] = field(default_factory=list)
    c: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.date)


def load_bars(path: str) -> Series:
    sym = os.path.splitext(os.path.basename(path))[0]
    s = Series(symbol=sym)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s.date.append(row["date"])
            s.o.append(float(row["open"]))
            s.h.append(float(row["high"]))
            s.l.append(float(row["low"]))
            s.c.append(float(row["close"]))
            s.v.append(float(row["volume"]))
    return s


# ─────────────────────── causal indicators ───────────────────────
# Every function returns a list the same length as the input, where element i
# depends only on inputs[0..i]. None means "not enough history yet".

def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    run = 0.0
    for i, x in enumerate(xs):
        run += x
        if i >= n:
            run -= xs[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(xs[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(xs)):
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = RSI_PERIOD) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def atr(h: list[float], l: list[float], c: list[float], n: int = ATR_PERIOD) -> list[float | None]:
    """Wilder's ATR."""
    out: list[float | None] = [None] * len(c)
    if len(c) < n + 1:
        return out
    trs = [h[0] - l[0]]
    for i in range(1, len(c)):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    prev = sum(trs[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(c)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def roc(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    for i in range(n, len(xs)):
        if xs[i - n]:
            out[i] = (xs[i] - xs[i - n]) / xs[i - n]
    return out


# ────────────────────────── signal detection ──────────────────────────
@dataclass
class Signal:
    symbol: str
    idx: int            # bar index of the TRIGGER close (entry is idx+1)
    date: str
    trigger_close: float
    stop: float
    target: float


@dataclass
class Trade:
    symbol: str
    signal_date: str
    entry_date: str
    entry: float
    stop: float
    target: float
    exit_date: str = ""
    r_multiple: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""


class Indicators:
    """Precomputed causal indicator arrays for one symbol."""

    def __init__(self, s: Series):
        self.sma_fast = sma(s.c, SMA_FAST)
        self.sma_slow = sma(s.c, SMA_SLOW)
        self.ema20 = ema(s.c, EMA_PERIOD)
        self.rsi = rsi(s.c)
        self.atr = atr(s.h, s.l, s.c)
        self.roc20 = roc(s.c, RS_LOOKBACK)
        self.vol_avg = sma(s.v, VOL_AVG_LOOKBACK)
        dollar = [s.c[i] * s.v[i] for i in range(len(s))]
        self.adv = sma(dollar, VOL_AVG_LOOKBACK)


def _regime_ok(spy: Series, spy_ind: Indicators, j: int) -> bool:
    """SPY above its 50-SMA. [HARD] below the 200-SMA, P1 longs are suspended."""
    f, sl = spy_ind.sma_fast[j], spy_ind.sma_slow[j]
    if f is None or sl is None:
        return False
    if spy.c[j] < sl:      # bear tape — suspended entirely
        return False
    return spy.c[j] > f


def find_signals(s: Series, ind: Indicators, spy: Series, spy_ind: Indicators,
                 spy_idx_by_date: dict[str, int],
                 target_mode: str = "prior_high") -> list[Signal]:
    sigs: list[Signal] = []
    start = max(SMA_SLOW, HIGH_52W_LOOKBACK, TARGET_LOOKBACK) + 2

    for i in range(start, len(s) - 1):     # -1: need bar i+1 to enter on
        # ---- universe ----
        if s.c[i] < MIN_PRICE:
            continue
        if ind.adv[i] is None or ind.adv[i] < MIN_ADV_DOLLARS:
            continue

        # ---- market regime (uses SPY at the SAME date) ----
        j = spy_idx_by_date.get(s.date[i])
        if j is None or not _regime_ok(spy, spy_ind, j):
            continue

        # ---- trend structure ----
        f, sl = ind.sma_fast[i], ind.sma_slow[i]
        if f is None or sl is None:
            continue
        if not (s.c[i] > f > sl):
            continue
        prev_f = ind.sma_fast[i - SMA_SLOPE_LOOKBACK]
        if prev_f is None or f <= prev_f:          # 50-SMA must be rising
            continue
        high_252 = max(s.h[i - HIGH_52W_LOOKBACK + 1:i + 1])
        if high_252 <= 0 or (high_252 - s.c[i]) / high_252 > MAX_PCT_BELOW_HIGH:
            continue

        # ---- pullback ----
        lo_w = i - SWING_LOOKBACK + 1
        swing_high = max(s.h[lo_w:i + 1])
        sh_idx = lo_w + s.h[lo_w:i + 1].index(swing_high)
        if sh_idx >= i:                             # swing high is today: no pullback yet
            continue
        pull_low = min(s.l[sh_idx:i + 1])
        retrace = (swing_high - pull_low) / swing_high
        if not (RETRACE_MIN <= retrace <= RETRACE_MAX):
            continue
        e20 = ind.ema20[i]
        if e20 is None or pull_low > e20 * (1 + EMA_PROXIMITY):
            continue                                # never came back to the 20-EMA
        # pullback on declining volume vs the impulse leg before the swing high
        if sh_idx - VOL_AVG_LOOKBACK // 2 < 0:
            continue
        pull_vol = statistics.fmean(s.v[sh_idx:i + 1])
        impulse_vol = statistics.fmean(s.v[sh_idx - 10:sh_idx])
        if impulse_vol <= 0 or pull_vol >= impulse_vol:
            continue

        # ---- RSI fell into 40-55 and turned up ----
        window = [x for x in ind.rsi[i - RSI_WINDOW + 1:i + 1] if x is not None]
        if len(window) < RSI_WINDOW:
            continue
        trough = min(window)
        if not (RSI_BAND_LO <= trough <= RSI_BAND_HI):
            continue
        if trough < RSI_FLOOR:
            continue
        if ind.rsi[i] is None or ind.rsi[i - 1] is None or ind.rsi[i] <= ind.rsi[i - 1]:
            continue                                # has not turned up

        # ---- relative strength vs SPY over 20 sessions ----
        r_sym, r_spy = ind.roc20[i], spy_ind.roc20[j]
        if r_sym is None or r_spy is None or r_sym <= r_spy:
            continue

        # ---- entry trigger ----
        if s.c[i] <= s.h[i - 1]:
            continue
        if ind.vol_avg[i] is None or s.v[i] < ind.vol_avg[i]:
            continue

        # ---- stop from structure, then the 12% rejection ----
        a = ind.atr[i]
        if a is None:
            continue
        stop = min(pull_low, s.c[i] - ATR_STOP_MULT * a)
        if stop <= 0 or stop >= s.c[i]:
            continue
        if (s.c[i] - stop) / s.c[i] > MAX_STOP_PCT:
            continue

        # ---- structural target and the 2.0 minimum reward:risk ----
        # P1 says the target comes from "prior high, measured move, or a
        # resistance level" without choosing. target_study.py shows the choice
        # decides whether P1 can trade AT ALL: against a prior high, 0 of 341
        # candidates in 15 years clear 2.0R, because the trigger fires only
        # after price has already recovered toward that high.
        if target_mode == "prior_high":
            target = max(s.h[i - TARGET_LOOKBACK + 1:i + 1])
        else:   # measured_move: project the pullback's depth above the swing high
            target = swing_high + (swing_high - pull_low)
        if target <= s.c[i]:
            continue                                # no structural target above entry
        if (target - s.c[i]) / (s.c[i] - stop) < MIN_RR:
            continue

        sigs.append(Signal(s.symbol, i, s.date[i], s.c[i], stop, target))
    return sigs


# ────────────────────────────── execution ──────────────────────────────
def simulate(s: Series, ind: Indicators, sig: Signal, stop_model: str) -> Trade | None:
    """Enter at sig.idx+1 and manage forward. Returns None if the limit never filled
    or the trade was voided by the gap rule."""
    e = sig.idx + 1
    if e >= len(s):
        return None

    # [HARD] gap-void: more than 2% above the trigger close and the trade is gone.
    if s.o[e] > sig.trigger_close * (1 + MAX_GAP_UP):
        return None

    # Limit at or below the trigger close.
    if s.o[e] <= sig.trigger_close:
        entry = s.o[e]
    elif s.l[e] <= sig.trigger_close:
        entry = sig.trigger_close
    else:
        return None                                   # limit never touched

    stop0 = sig.stop
    if entry <= stop0:
        return None
    # §6 step 5 re-verifies the [HARD] rules against the ACTUAL fill, not the plan.
    if (entry - stop0) / entry > MAX_STOP_PCT:
        return None
    if (sig.target - entry) / (entry - stop0) < MIN_RR:
        return None

    R = entry - stop0
    t = Trade(s.symbol, sig.date, s.date[e], entry, stop0, sig.target)

    cur_stop = stop0
    remaining = 1.0
    realized = 0.0
    hit_1r = False
    hit_2r = False
    below_ema = 0
    pending_exit = ""     # decided on a close, executed at the next open

    d = e
    while d < len(s):
        held = d - e

        # A signal-based exit decided yesterday executes at today's open.
        if pending_exit:
            realized += remaining * (s.o[d] - entry) / R
            t.exit_date, t.exit_reason = s.date[d], pending_exit
            remaining = 0.0
            break

        # 1. Stop first. Within a single bar we cannot know whether the stop or
        #    the target was touched first, so we assume the stop — the
        #    conservative choice, and the one that avoids flattering the result.
        if stop_model == "intraday":
            if s.l[d] <= cur_stop:
                fill = min(s.o[d], cur_stop)          # a gap-down fills below the stop
                realized += remaining * (fill - entry) / R
                t.exit_date, t.exit_reason = s.date[d], "stop"
                remaining = 0.0
                break
        else:  # close-based stop, as P1's exit table literally reads
            if s.c[d] < cur_stop:
                pending_exit = "stop"

        # 2. +2R: trim half, trail the rest at 1.5 ATR.
        if remaining == 1.0 and not hit_2r and s.h[d] >= entry + 2 * R:
            realized += 0.5 * (entry + 2 * R - entry) / R      # = 1.0R on half
            remaining = 0.5
            hit_2r = hit_1r = True
            # Reaching +2R necessarily passed +1R, so the breakeven trail applies
            # too. Setting hit_1r above without this would skip step 3 entirely
            # and leave the remaining half exposed to a full -1R from entry.
            cur_stop = max(cur_stop, entry)
            a = ind.atr[d]
            if a:
                cur_stop = max(cur_stop, s.c[d] - TRAIL_ATR_MULT * a)

        # 3. +1R: stop to breakeven.
        if not hit_1r and s.h[d] >= entry + R:
            hit_1r = True
            cur_stop = max(cur_stop, entry)

        # 4. Trail the remainder once half is off.
        if hit_2r and remaining > 0:
            a = ind.atr[d]
            if a:
                cur_stop = max(cur_stop, s.c[d] - TRAIL_ATR_MULT * a)

        # 5. Close-based signal exits, executed next open.
        if not pending_exit:
            e20 = ind.ema20[d]
            if e20 is not None and s.c[d] < e20:
                below_ema += 1
                if below_ema >= EMA_EXIT_CONSECUTIVE:
                    pending_exit = "ema20"
            else:
                below_ema = 0
            if not pending_exit and held >= TIME_STOP_SESSIONS and not hit_1r:
                pending_exit = "time_stop"

        d += 1

    if remaining > 0:      # ran out of data — close at the last bar
        realized += remaining * (s.c[-1] - entry) / R
        t.exit_date, t.exit_reason = s.date[-1], "end_of_data"

    t.r_multiple = realized
    t.bars_held = max(1, (d if d < len(s) else len(s) - 1) - e)
    return t


# ──────────────────────────────── report ────────────────────────────────
def run(stop_model: str, target_mode: str = "prior_high") -> dict:
    spy = load_bars(os.path.join(DATA_DIR, f"{BENCHMARK}.csv"))
    spy_ind = Indicators(spy)
    spy_idx = {d: i for i, d in enumerate(spy.date)}

    trades: list[Trade] = []
    n_signals = 0
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    symbols = 0
    first_date, last_date = None, None

    for path in files:
        s = load_bars(path)
        if s.symbol == BENCHMARK or len(s) < 400:
            continue
        symbols += 1
        first_date = min(first_date or s.date[0], s.date[0])
        last_date = max(last_date or s.date[-1], s.date[-1])
        ind = Indicators(s)
        sigs = find_signals(s, ind, spy, spy_ind, spy_idx, target_mode)
        n_signals += len(sigs)

        # One position per symbol at a time: a new signal while the previous
        # trade is still open is ignored, which is how the live system behaves
        # (it manages the open position rather than stacking another).
        busy_until = -1
        for sig in sigs:
            if sig.idx <= busy_until:
                continue
            tr = simulate(s, ind, sig, stop_model)
            if tr is None:
                continue
            trades.append(tr)
            busy_until = sig.idx + tr.bars_held

    return {
        "stop_model": stop_model,
        "target_mode": target_mode,
        "symbols": symbols,
        "first_date": first_date, "last_date": last_date,
        "signals": n_signals,
        "trades": trades,
    }


def summarize(res: dict) -> str:
    trades: list[Trade] = res["trades"]
    n = len(trades)
    out = []
    a = out.append
    a(f"P1 BACKTEST — stop model: {res['stop_model']}   target: {res['target_mode']}")
    a(f"  universe: {res['symbols']} symbols   period: {res['first_date']} .. {res['last_date']}")
    a(f"  signals generated: {res['signals']}")
    a(f"  trades taken:      {n}   (gap-voids and unfilled limits removed)")
    if not n:
        a("  no trades — nothing to evaluate")
        return "\n".join(out)

    rs = [t.r_multiple for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    total = sum(rs)
    avg = total / n

    # Max drawdown on the cumulative R curve (equal risk per trade).
    peak = cum = 0.0
    mdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)

    years = (int(res["last_date"][:4]) - int(res["first_date"][:4])) or 1
    a("")
    a(f"  win rate:        {len(wins)/n*100:5.1f}%   ({len(wins)}W / {len(losses)}L)")
    a(f"  average R:       {avg:+.3f}R per trade")
    a(f"  total:           {total:+.1f}R")
    a(f"  median R:        {statistics.median(rs):+.3f}R")
    a(f"  best / worst:    {max(rs):+.2f}R / {min(rs):+.2f}R")
    if wins:
        a(f"  avg win:         {statistics.fmean(wins):+.3f}R")
    if losses:
        a(f"  avg loss:        {statistics.fmean(losses):+.3f}R")
    a(f"  max drawdown:    {mdd:.1f}R")
    a(f"  avg hold:        {statistics.fmean([t.bars_held for t in trades]):.1f} sessions")
    a(f"  trade frequency: {n/years:.1f} per year across {res['symbols']} names "
      f"({n/years/res['symbols']:.2f} per name per year)")

    a("")
    a("  exits:")
    reasons: dict[str, list[float]] = {}
    for t in trades:
        reasons.setdefault(t.exit_reason, []).append(t.r_multiple)
    for reason, vals in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        a(f"    {reason:<12} {len(vals):>4}  ({len(vals)/n*100:4.1f}%)  avg {statistics.fmean(vals):+.3f}R")

    # Is the mean plausibly just noise? One-sample t on per-trade R.
    if n > 1:
        sd = statistics.stdev(rs)
        if sd > 0:
            tstat = avg / (sd / math.sqrt(n))
            a("")
            a(f"  std dev:         {sd:.3f}R")
            a(f"  t-statistic:     {tstat:+.2f}  (|t| > ~2 suggests the mean is not just noise)")
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest playbook P1.")
    p.add_argument("--stop-model", choices=["intraday", "close", "both"], default="both",
                   help="intraday = broker stop-limit (CLAUDE.md §6 step 9); "
                        "close = P1's exit table as literally written")
    p.add_argument("--target-mode", choices=["prior_high", "measured_move"],
                   default="prior_high",
                   help="how to read P1's 'structural target'")
    p.add_argument("--csv", default="", help="write per-trade rows to this path")
    args = p.parse_args()

    if not os.path.isdir(DATA_DIR) or not glob.glob(os.path.join(DATA_DIR, "*.csv")):
        print("No data. Run: py research/fetch_bars.py", file=sys.stderr)
        return 1

    models = ["intraday", "close"] if args.stop_model == "both" else [args.stop_model]
    last = None
    for m in models:
        last = run(m, args.target_mode)
        print(summarize(last))
        print()

    if args.csv and last:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["symbol", "signal_date", "entry_date", "entry", "stop", "target",
                        "exit_date", "exit_reason", "bars_held", "r_multiple"])
            for t in last["trades"]:
                w.writerow([t.symbol, t.signal_date, t.entry_date, f"{t.entry:.4f}",
                            f"{t.stop:.4f}", f"{t.target:.4f}", t.exit_date,
                            t.exit_reason, t.bars_held, f"{t.r_multiple:.4f}"])
        print(f"per-trade rows written to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
