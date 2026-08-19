# P4 — 0DTE INTRADAY

**Tier:** T4 only (≥ $25,000). **Locked below that — no exceptions.**

---

## WHY THIS IS LOCKED BELOW $25,000

Three independent hard blocks, any one of which is disqualifying:

**1. PDT.** Every 0DTE round trip is a day trade. Under $25,000 in a
`limited_margin` account you get **3 per rolling 5 business days**. A strategy
whose entire premise is intraday cannot run at 3 trades per week — and the 4th
flags the account for 90 days. The strategy and the account type are
structurally incompatible below the threshold.

**2. Contract cost.** SPY at 1.5 DTE, ATM, quoted $1.98/$2.00 — **$199 per
contract.** At P4's reduced 2% risk cap, one contract requires a **$9,950**
account. So cost alone binds around $10,000 — it is PDT (block 1) that pushes the
real gate to $25,000. Both must clear; PDT is the tighter of the two.

**3. Gamma.** On expiry day, delta reprices violently. A position can go from
+40% to −80% inside a minute, faster than any stop can be worked. Position sizing
everywhere else in this system assumes stops are reachable. On 0DTE they
frequently are not — you can lose substantially more than intended between two
prints. That is why P4's per-trade budget is cut from 5% to **2%**.

---

## IF AND ONLY IF T4 IS REACHED

Additional constraints layered on top of the full constitution:

```
[HARD] MAX_RISK_TRADE for P4 = 0.02 * ACCOUNT     # 2%, not 5% — gamma slippage
[HARD] Max 2 P4 trades per session
[HARD] Max 1 P4 position open at a time
[HARD] Daily P4 loss limit = 0.04 * ACCOUNT → P4 disabled for the session
[HARD] 3 consecutive P4 losing sessions → P4 disabled pending operator review
[HARD] SPY / QQQ only. Nothing else has the book depth.
[HARD] No entries after 14:30 ET — terminal gamma
[HARD] No entries in the first 15 minutes
[HARD] Every position flat by 15:45 ET. Never held to settlement.
```

**Setup:** opening-range breakout, 09:45–10:30 ET only. Range defined by the
first 15 minutes. Entry on a break with volume confirmation and SPY trading in
the direction of its own 5-day trend.

**Contract:** ATM or one strike ITM, delta ≥ 0.45. Never OTM.

**Exits:** +40% premium → close half, trail. −35% premium → close full, no
discretion. 15:45 ET → flat regardless.

**Sizing assumes 100% loss, not −35%.** Contracts are sized against total loss of
premium. On 0DTE the −35% stop is the *least* reliable stop in this system —
block 3 above is precisely the observation that gamma can carry price through it
between two prints. Never size as though −35% caps the loss. Use:

```bash
py engine/risk_engine.py size-option --account <live> --premium <mark> --playbook P4
```

which applies the 2% P4 budget rather than the 5% default.

---

## THE HONEST NOTE

0DTE is the highest-variance instrument retail can access. Its popularity is
driven by the size of the wins, which are real, and the reporting of the losses,
which is not. Public P&L on this instrument is heavily survivorship-filtered.

If P4 is enabled, run it on a strictly partitioned sleeve of capital and evaluate
it as a separate book with its own equity curve. Do not let P4 results influence
sizing anywhere else, and do not let profits from P1–P3 subsidize a P4 sleeve
that is not carrying itself over a meaningful sample.
