# P3 — THE WHEEL (Cash-Secured Puts → Assignment → Covered Calls)

**Tier:** T3+ ($10,000 minimum — see capital requirement below)
**Instrument:** Short cash-secured puts; short calls against owned shares. Single leg.
**Holding period:** 9–24 days per leg (enter 30–45 DTE, close at 21 DTE); a full
CSP → assignment → covered-call cycle typically runs 6–12 weeks

---

## CAPITAL REQUIREMENT — why T3

A cash-secured put requires collateral for 100 shares at the strike. Live
examples:

| Underlying | Price | 100 shares | CSP collateral |
|---|---|---|---|
| F | $14.50 | $1,450 | ~$1,500 |
| SOFI | $18.44 | $1,844 | ~$1,800 |
| PLTR | $175.19 | $17,519 | ~$17,000 |
| SPY | $769.06 | $76,906 | ~$76,000 |

**[HARD]** CSP collateral ≤ 25% of account. At $10,000 that permits underlyings
up to ~$25/share. Below $10,000 the wheel forces either dangerous concentration
in a single position or a universe restricted to sub-$10 stocks, which are
exactly the names you least want to be assigned. Hence the tier gate.

---

## THE PREMISE

You are paid premium to accept an obligation to buy a stock at a price you chose.
This is only a good trade if **you actually want to own the stock at that
strike.** Strip that condition away and the wheel becomes selling insurance
against a crash on a name you have no interest in holding, for a few dollars.

**[HARD]** Do not sell a cash-secured put on any underlying that fails the
ownership test below. Premium yield is never sufficient justification on its own.

### Ownership test — all required
- The name passes the P1 universe filter
- You would hold it for 6+ months if assigned
- Not in secular decline; not a turnaround story; not meme-driven
- Profitable, or clearly cash-generative — check `get_financials` /
  `get_equity_fundamentals`
- Strike is at or below a level you consider fair value

---

## LEG 1 — CASH-SECURED PUT

**Selection**
- Delta 0.20–0.30 (roughly 70–80% probability of expiring worthless)
- 30–45 DTE
- Annualized yield ≥ 12% — `(premium / strike) * (365 / DTE)`
- **[HARD]** No earnings before expiry
- **[HARD]** IV rank ≥ 30 — selling premium in a low-IV regime pays too little
  for the tail risk assumed
- All §2.5 liquidity gates pass

**Sizing** — **[HARD]** use the engine:

```bash
py engine/risk_engine.py size-csp \
  --account <live> --cash <cash on hand> --strike <strike> --symbol <SYM>
```

The caps it applies:

```
collateral = strike * 100 * contracts

[HARD] collateral (single position)  <= 0.25 * ACCOUNT
[HARD] ALL options exposure          <= 0.40 * ACCOUNT   # MAX_OPTIONS_EXP, §2.1
[HARD] symbol exposure               <= 0.30 * ACCOUNT   # shares + options combined
[HARD] cash on hand                  >= total collateral # verify via get_portfolio
```

**There is no separate, looser aggregate ceiling for CSPs.** An earlier draft of
this file set "total across all open CSPs ≤ 50% of account," which contradicted
the constitution's blanket 40% cap on options exposure. CSP collateral **is**
options exposure and is counted by `MAX_OPTIONS_EXP`. The 40% ceiling is the only
one. Pinned by `test_no_path_allows_options_above_40_percent`.

**Management**
| Trigger | Action |
|---|---|
| 50% of max profit captured | Close early. Best risk-adjusted exit in the book. |
| 21 DTE reached | Close or roll. Do not hold into gamma risk. |
| Underlying drops below strike, thesis intact | Accept assignment → Leg 2 |
| Underlying drops below strike, thesis broken | Close the put, take the loss, exit the name |
| Assignment | Log the cost basis as `strike - premium_received` |

**[HARD]** Never roll a put down and out purely to avoid realizing a loss. Roll
only if you still want the shares and the new strike still passes the ownership
test. Rolling to avoid a loss is averaging down with extra steps.

---

## LEG 2 — COVERED CALL

Entered only after assignment. Requires **100 whole shares** per contract.

**[HARD] Assignment changes your symbol exposure, and you must re-check it.** A
CSP sized at 25% of account converts on assignment into ~25% of account held in
that stock. If P1 also holds shares of the same name, combined exposure may now
exceed `MAX_SYMBOL_EXP` (30%). On assignment: recompute with
`risk_engine.symbol_exposure()` immediately, and if the combined position breaches
30%, reduce the **P1** leg — it has a defined stop and a thesis you can test.
Never reduce assigned shares just to make room for a P1 trade.

**[HARD]** Fractional shares from P1 cannot back a covered call. Only whole
100-lots from assignment count. See the interaction section in
`P1_equity_momentum.md`.

**Selection**
- Delta 0.20–0.30
- 30–45 DTE
- **[HARD]** Strike ≥ your cost basis. Never sell a call below basis. Doing so
  locks in a loss to collect premium and is prohibited.
- **[HARD]** No earnings before expiry

**Management**
| Trigger | Action |
|---|---|
| 50% of max profit | Close early, resell further out |
| Called away | Cycle complete. Log total P&L. Return to Leg 1. |
| Stock rallies hard through strike | Let it be called. Do not chase by rolling up. |
| Stock drops materially | Hold shares, continue selling calls at or above basis |

**[HARD]** Being called away is a successful outcome, not a loss. Do not roll a
covered call up and out to "save" the shares — that converts a completed
profitable cycle into an uncapped directional bet.

---

## INVALIDATION

The wheel's real risk is not assignment. It is being assigned into a name that
keeps falling, then selling calls below basis to feel productive while the
position bleeds. Record at entry: the price at which you exit the underlying
entirely, thesis broken, regardless of premium collected.
