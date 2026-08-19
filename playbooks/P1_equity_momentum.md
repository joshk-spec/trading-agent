# P1 — EQUITY MOMENTUM / TREND CONTINUATION

**Tier:** T0+ (active at all account sizes)
**Instrument:** Common shares, fractional permitted
**Holding period:** 2–20 sessions
**Why this is the T0 playbook:** fractional shares divide arbitrarily, so the
Minimum Viable Unit problem (§2.3) does not exist. Risk can be sized to spec at
any account value. No expiry, no theta, no assignment, no spread tax worth
mentioning on liquid names. It is the only strategy that is *mechanically*
correct below $700.

---

## UNIVERSE

**[HARD]** Symbol must satisfy all:
- Price ≥ $5.00 (avoid sub-$5 microstructure and margin ineligibility)
- 20-day average dollar volume ≥ $50,000,000
- Bid-ask spread ≤ 0.15% of last
- Optionable and listed on a primary US exchange
- No earnings within the intended holding horizon
- Not a leveraged/inverse ETF, not a recent IPO (< 6 months), not a biotech
  pending an FDA catalyst

Build the candidate list with `run_scan` / `get_equity_technical_indicators`.
Re-verify liquidity per name with `get_equity_quotes` before every entry.

---

## SETUP — all conditions required

**Trend structure**
- Price > 50-day SMA > 200-day SMA
- 50-day SMA slope positive over the trailing 10 sessions
- Price within 8% of its 52-week high

**Pullback**
- A retracement of 3–10% from a swing high, into or near the 20-day EMA
- Pullback occurred on declining volume relative to the impulse leg
- RSI(14) fell to 40–55 and has turned up — not below 30 (that is a downtrend)

**Relative strength**
- The name outperformed SPY over the trailing 20 sessions

**Market regime**
- SPY above its own 50-day SMA. **[HARD]** If SPY is below its 200-day SMA, P1
  longs are suspended entirely. Do not fight a bear tape with a trend-following
  system; the base rate collapses.

> **P1 is long-only.** Short selling is not reliably available in a
> `limited_margin` account, so there is no short branch and no criteria are
> defined for one. Do not construct a short setup. Do not substitute long puts
> either — bearish trades live in P2, which has its own tier gate and its own
> (separately specified) bearish setup.

---

## ENTRY TRIGGER

Price closes above the prior session's high, on volume ≥ the 20-day average.

Enter on the **following** session via limit order at or below the trigger
close. **[HARD]** If price gaps more than 2% above the trigger, the trade is
void. Do not chase.

---

## SIZING

Determine the stop from structure first, then let the engine size it. **[HARD]**
Do not compute share count by hand.

```
stop_price = min(swing_low_of_pullback, entry - 2.0 * ATR(14))
```

```bash
py engine/risk_engine.py size-equity \
  --account <live> --entry <entry> --stop <stop_price> --symbol <SYM>
```

The engine applies, in order: `MAX_RISK_TRADE` → `MAX_POS_NOTIONAL` (25%) →
remaining `MAX_SYMBOL_EXP` room (30%, **summed across shares and options in this
underlying**) → `MAX_CONCURRENT` (5). It returns the share count, the realized
risk, and which cap bound.

**[HARD]** `risk_per_share / entry <= 0.12`. A stop wider than 12% of entry means
the name is too volatile for this playbook — skip it. The engine rejects these.

**What risk you are actually taking.** Because the notional cap is 25% and the
widest permitted stop is 12%, P1's arithmetic ceiling is 25% × 12% = **3.0% of
account**, and a typical setup lands nearer **1.5%**. The 5% figure in §2.1 is a
portfolio-wide ceiling, not a P1 target, and P1 cannot reach it. Journal the
engine's `risk_pct`.

**[HARD]** Never widen the stop to fit a larger position. That inverts the entire
logic of position sizing — the stop defines the risk, the risk defines the size,
never the reverse.

---

## EXITS

| Trigger | Action |
|---|---|
| Stop hit (close below `stop_price`) | Exit full. Non-negotiable. |
| +1R unrealized | Trail stop to breakeven |
| +2R unrealized | Trim 1/2, trail remainder at 1.5 ATR |
| Close below 20-day EMA for 2 consecutive sessions | Exit full |
| 20 sessions elapsed without reaching +1R | Exit full — thesis expired |
| Earnings date enters the horizon | Exit before the print. Always. |

**[HARD]** Minimum reward:risk at entry is 2.0. Compute the target from real
structure — prior high, measured move, or a resistance level — not by
multiplying the stop by two and calling it a target.

---

## INTERACTION WITH P3 — fractional shares block covered calls

**[HARD]** A covered call requires **100 whole shares**. P1 buys fractional
shares, so a P1 position of 47.3 shares cannot be used as P3 collateral, and a
P1 position of 147.3 shares can cover exactly one contract with 47.3 shares
stranded.

If both playbooks are live on the same underlying:
- P1 and P3 holdings in one name are a **single** `MAX_SYMBOL_EXP` exposure. Sum
  them. The engine does this for you.
- Never buy fractional shares with the intent of reaching 100 to sell a call.
  That is a P3 entry executed through the wrong playbook, and P3's ownership test
  and tier gate exist precisely to prevent it.
- Shares acquired by P3 assignment are P3's, tracked at the assignment basis.
  Shares bought by P1 are P1's, tracked at the P1 entry with a P1 stop. Do not
  merge the two books because the ticker matches.

---

## INVALIDATION

Record at entry, in the journal: *"This thesis is wrong if ______."*

For P1 it is normally: a close below the pullback swing low, or SPY losing its
50-day SMA while the position is open. Write the specific price. A thesis without
a falsifier is not a thesis.
