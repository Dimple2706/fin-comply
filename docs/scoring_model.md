# DPDP compliance scoring model

This document details the deterministic, state-aware compliance scoring and risk scoring model implemented in the engine.

## 1. Compliance Score Formula

The top-level compliance score is computed dynamically based on the final execution states of all enabled active rules.

$$Compliance\ Score\ = \frac{|P|}{|V| + |P| + |A| + |F|} \times 100.0$$

Where the active rule sets are classified as:
- **$P$ (PASS)**: The rule executed successfully, evidence was present, and no violations were detected.
- **$V$ (VIOLATION)**: The rule executed successfully, evidence was present, and one or more violations were detected.
- **$A$ (NOT_ASSESSABLE)**: The rule executed successfully, but required evidence was missing (e.g. missing justification or incomplete breach confirmation fields).
- **$F$ (FAILED)**: Rule execution failed during database query loading, SQL execution, or native evaluator run.

### Denominator Rules & State Handling
- **NOT_APPLICABLE ($N$)**: If a rule genuinely does not apply to the evaluated tenant system/records (e.g. no minor data present for `DPDP-005`), it is excluded from the denominator entirely ($r \notin \text{denominator}$). It does not penalize or improve the compliance percentage.
- **NOT_ASSESSABLE ($A$) & FAILED ($F$)**: These represent gaps in evidence or execution sanity. They are included in the denominator but excluded from the numerator (satisfied counts). This ensures that missing evidence or execution failures reduce the score and cannot silently present a false compliance state.

### Fallback
If the denominator evaluates to `0` (all rules are `NOT_APPLICABLE`), the compliance score defaults to `100.0%`.

---

## 2. Risk Score & Normalization

The risk score is a normalized penalty metric ($0$ to $100$) showing audit risk exposure:

$$Risk\ Score = \min\left(\frac{\sum_{r \in V} \text{risk\_contribution}(r)}{\sum_{r \notin N} \text{risk\_weight}(r)} \times 100.0, 100.0\right)$$

Where:
- **Denominator ($\sum_{r \notin N} \text{risk\_weight}(r)$)**: Dynamically computed from active DB rules excluding any `NOT_APPLICABLE` rules. This prevents distortion and maintains consistency with the compliance score.
- **Severity Floor Policies**:
  - Any `CRITICAL` violation forces a minimum risk score of `65.0` (guaranteeing a `HIGH` risk tier).
  - Accumulation of 3+ `HIGH` severity violations forces a minimum risk score of `45.0` (guaranteeing a `MEDIUM` risk tier).

---

## 3. Duplicate Prevention & Deduplication

To prevent repeated database records or duplicate signal evaluations from distorting prevalence metrics, rule violations are strictly deduplicated by record identity:
- For each rule, violations are grouped and deduplicated by their unique `record_id` (representing the primary database record hash).
- Only unique record IDs contribute to `affected_rows` and the likelihood prevalence ratio.
- This ensures that duplicate database rows do not inflate the computed prevalence, risk, or compliance metrics.

---

## 4. Penalty Exposure Wording

All monetary penalties and exposure totals computed by the engine are maximum legal liability guidelines and must be presented with the following disclaimer:

> [!IMPORTANT]
> **Maximum statutory exposure estimate — not an actual or certain fine.**
> The monetary figures represent the maximum possible exposure under the DPDP Act based on severity class limits, and do not constitute an actual or guaranteed fine.
