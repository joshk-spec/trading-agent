# Hypothesis NNN — <one line>

**Mechanism:** <Why should this edge exist? Who is on the other side of the
trade, and what constraint makes them transact at a disadvantage? Two sentences.
If you cannot write this, do not test the idea.>

**Universe:** <symbols, and why these and not others>

**Exact rules:**
- Entry:
- Stop:
- Target:
- Exit:
- Sizing:

**Parameters:** <every number, fixed now, each with the reason it takes this
value. No ranges. A range is two hypotheses.>

**Success criteria — all required:**
- avg R ≥ +0.10 after 0.10% round-trip costs
- t ≥ 2.0 (divided by tests-run-so-far, per the ledger)
- trades ≥ 100 on the train set

**Kill criterion:** <what result makes you abandon this — state it now, while you
have no stake in the answer>

**Tests used so far:** <from TEST_LEDGER.md>

---
*Commit this file before the first run. A hypothesis written after seeing results
is not a hypothesis; the commit timestamp is the evidence that it wasn't.*
