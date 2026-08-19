# P2 — DIRECTIONAL SWING OPTIONS

**Tier:** T1+ ($700 minimum, reduced size until T2 / $2,500)
**Instrument:** Long calls, long puts. Single leg. Never short premium here.
**Holding period:** 5–30 sessions
**Max loss:** premium paid. This is the entire appeal and the entire trap.

---

## THE PREMISE, STATED HONESTLY

A long option must be right about **direction, magnitude, and timing
simultaneously**. Equity requires only direction. You accept that much harder
problem in exchange for leverage and a capped, known downside.

That trade is worth making only when the expected move materially exceeds what
the option prices in. If you are not explicitly comparing your expected move to
the breakeven, you are buying a lottery ticket and calling it a strategy.

**[HARD]** Every P2 entry records, in the journal: expected move (%), the
contract's breakeven move (%), and the ratio. **Ratio must be ≥ 1.5.**

---

## UNDERLYING SELECTION

**[HARD]** Underlying must pass the full P1 universe filter, plus:
- Options open interest ≥ 5,000 across the chain
- Weekly expirations available
- IV rank ≤ 50. **[HARD]** Do not buy premium in the top half of its own IV
  range. You are structurally short volatility-crush when you do.

### Bullish leg — long calls
Setup criteria: identical to P1's SETUP section. P2 calls are P1 expressed with
leverage, not a separate thesis engine. If the P1 setup is absent, there is no
long call.

### Bearish leg — long puts
P1 is long-only and its criteria are all bullish, so **a put cannot inherit
them.** Its mirror, all conditions required:

- Price < 50-day SMA < 200-day SMA
- 50-day SMA slope negative over the trailing 10 sessions
- Price within 8% of its 52-week **low**
- A **rally** of 3–10% off a swing low, into or near the 20-day EMA
- RSI(14) rose to 45–60 and has turned **down** — not above 70 (that is an uptrend)
- The name **underperformed** SPY over the trailing 20 sessions
- **[HARD]** Market regime: SPY **below** its 50-day SMA. If SPY is above its
  200-day SMA, long puts are suspended entirely — the mirror of P1's rule, and
  for the same reason. Do not fight the tape in either direction.
- Entry trigger: price closes **below** the prior session's low on volume ≥ the
  20-day average. Enter the following session. **[HARD]** If price gaps more than
  2% below the trigger, the trade is void.

**[HARD]** Long puts require the full bearish set above. Never open a put because
a bullish setup "looks tired," and never open one as a hedge — this system has no
hedging playbook, and an unhedged rule invented at runtime is discretionary
trading (§4).

---

## CONTRACT SELECTION — in this order, never reordered

1. **Expiry:** **[HARD]** 30–60 DTE at entry. Nothing shorter, nothing longer.
   (The 21-DTE figure elsewhere in this file is the *exit* trigger, not an entry
   floor — entries never come close to it.)
2. **Strike:** **[HARD]** delta must be **0.55–0.70**. Slightly ITM. This is a
   single enforceable range, not a target with a looser floor — an earlier draft
   named 0.55–0.70 as guidance and 0.40 as the hard limit, which left 0.40–0.55
   ambiguous. It is not permitted. Cheap OTM contracts have low probability of
   profit and exist to look affordable, which is exactly the failure mode §2.3
   guards against.
3. **Liquidity:** all gates in §2.5 must pass on the specific contract.
4. **Only now**, compute size.

**[HARD]** Selecting a contract because it fits the budget, rather than because
it fits the thesis, is prohibited. The order of these four steps is the rule.

---

## SIZING

**[HARD]** Size with the engine. Do not compute contract counts by hand.

```bash
py engine/risk_engine.py size-option --account <live> --premium <mark> --symbol <SYM>
```

It enforces: MVU (`contracts >= 1`, else skip) → the T1 20%-per-contract rule →
`MAX_POS_NOTIONAL` (25%) → `MAX_SYMBOL_EXP` (30%, summed with any equity you hold
in the same name) → `MAX_OPTIONS_EXP` (40%, including any CSP collateral) →
`MAX_CONCURRENT` (5).

**Why sizing assumes a 100% loss when the stop is −50%.** Contracts are sized
against total loss of premium, not against the −50% stop. That is deliberate and
not an inconsistency: a long option can gap through −50% overnight on a bad print,
and the stop is not guaranteed reachable. Sizing for the worst case and stopping
earlier means realized loss on a stopped trade is roughly **half** the sized risk.
Journal both — the engine's `risk_dollars` is the sized (worst-case) figure.

Worked at $100: budget $5. Cheapest liquid ATM contract ≈ $33.50.
`floor(5 / 33.5) = 0` ⇒ **skip**. Correct output at T0, not a bug to work around.

Worked at $3,000: budget $150. A $1.40 contract costs $140. `floor(150/140) = 1`
⇒ 1 contract, $140 sized risk = 4.67% of account. Passes 25% notional. Valid.

---

## EXITS

| Trigger | Action |
|---|---|
| **+50% premium** | Trim 1/2. Record a breakeven exit level for the remainder in the journal and act on it next session — it is a written rule, not a "mental stop." |
| **+100% premium** | Trim 1/2 of remainder |
| **−50% premium** | Exit full. Hard stop. |
| **21 DTE** | Exit full regardless of P&L. **[HARD]** No exceptions. |
| Underlying breaks the P1 structural stop | Exit full |
| IV rank rises above 70 while profitable | Take profit — you are now short a crush |
| 5 sessions with no progress toward thesis | Exit — timing was wrong, and timing is one of your three required calls |

**[HARD]** The 21-DTE rule is absolute. Theta acceleration inside three weeks
destroys more retail option positions than direction ever has. It applies to
winners, losers, and positions you feel strongly about.

**[HARD]** Never hold a long option through expiry hoping. Never exercise for
intrinsic value when selling captures intrinsic plus remaining extrinsic.

---

## INVALIDATION

Record the underlying price that voids the thesis and the date by which the move
must begin. Both. A P2 position has two independent ways to be wrong and both
must be written down at entry.
