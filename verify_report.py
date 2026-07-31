"""
Integration test:
  1. Run run_compliance_analysis for tenant_a and TENANT-001
  2. Verify all five sections present and narration fields populated
  3. Print one full explainable_insights entry from TENANT-001
  4. PII boundary test
"""

import json
import sys
import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from src.agent_layer.orchestrator import run_compliance_analysis

DIVIDER = "\n" + "=" * 70 + "\n"

def verify_tenant(tenant_id: str):
    print(f"{DIVIDER}TENANT: {tenant_id}{DIVIDER}")
    r = run_compliance_analysis(tenant_id)

    # 1. Five keys present?
    required_keys = ["violation_report", "risk_insights", "compliance_score",
                     "mapped_regulations", "explainable_insights"]
    missing = [k for k in required_keys if k not in r]
    print(f"[1] Required keys {'OK' if not missing else 'MISSING: ' + str(missing)}")

    # 2. violation_report sorted correctly?
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    vr = r.get("violation_report", [])
    orders = [sev_order.get(e["severity"], 99) for e in vr]
    sorted_ok = orders == sorted(orders)
    print(f"[2] violation_report severity sort: {'OK' if sorted_ok else 'WRONG'} -> {[e['severity'] for e in vr]}")

    # 3. mapped_regulations has legal_title from DB?
    mr = r.get("mapped_regulations", [])
    has_legal_title = all(e.get("legal_title") for e in mr)
    print(f"[3] mapped_regulations legal_title populated: {'OK' if has_legal_title else 'MISSING'} ({len(mr)} entries)")

    # 4. At least one grounded narration?
    ei = r.get("explainable_insights", [])
    grounded = [e for e in ei if e.get("grounded") is True]
    fallback  = [e for e in ei if e.get("grounded") is False]
    print(f"[4] Grounded (Gemini): {len(grounded)} | Fallback: {len(fallback)}")
    for e in grounded[:3]:
        print(f"     grounded=True: {e['rule_id']}")
    for e in fallback[:3]:
        print(f"     grounded=False: {e['rule_id']} — {e.get('fallback_reason','')[:80]}")

    # 5. Arithmetic check
    cs = r.get("compliance_score", {})
    total = cs.get("violated_obligations", 0) + cs.get("warning_obligations", 0) + cs.get("satisfied_obligations", 0)
    print(f"[5] compliance_score arithmetic: {cs.get('violated_obligations')} V + "
          f"{cs.get('warning_obligations')} W + {cs.get('satisfied_obligations')} S = {total} "
          f"({'OK' if total == 19 else 'WRONG — expected 19'})")
    print(f"    score_percentage: {cs.get('score_percentage')}%")

    return r

# ── Run both tenants ──────────────────────────────────────────────────────────
r_a = verify_tenant("tenant_a")
r_b = verify_tenant("TENANT-001")

# ── Print one full explainable_insights entry from TENANT-001 ─────────────────
print(f"{DIVIDER}FULL EXPLAINABLE INSIGHT — TENANT-001 (first CRITICAL rule){DIVIDER}")
ei_b = r_b.get("explainable_insights", [])
critical_entry = next(
    (e for e in ei_b if any(
        v["severity"] == "CRITICAL"
        for v in r_b.get("violation_report", [])
        if v["rule_id"] == e["rule_id"]
    )),
    ei_b[0] if ei_b else None
)
if critical_entry:
    # print without full signal_attribution to keep output readable
    display = {k: v for k, v in critical_entry.items() if k != "signal_attribution"}
    print(json.dumps(display, indent=2, default=str))
    print("\nsignal_attribution:")
    for sa in critical_entry.get("signal_attribution", []):
        print(f"  {sa['signal_id']} fired={sa['fired']} weight={sa['weight']}: {sa['description']}")

# ── PII Boundary Test ─────────────────────────────────────────────────────────
print(f"{DIVIDER}PII BOUNDARY TEST{DIVIDER}")
from src.explainability.llm_narrator import narrate_violation, PIIBoundaryError

try:
    result = narrate_violation(
        rule_id="DPDP-TEST",
        rule_name="Test Rule",
        dpdp_section="Section X",
        legal_text="This is a test obligation.",
        fired_signals=[
            {
                "signal_id": "S1",
                "description": "User contact is test@example.com — check this field",
                "weight": 1.0,
            }
        ],
    )
    print("FAIL — PII not caught! Got:", result)
except PIIBoundaryError as e:
    print(f"OK — PIIBoundaryError raised and Gemini call blocked.")
    print(f"     Message: {e}")
except Exception as e:
    print(f"UNEXPECTED exception type {type(e).__name__}: {e}")
