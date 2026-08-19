"""
Multi-Tenant Test Data Generator for Fin-Comply Engine
======================================================
Generates schema-aligned synthetic CSV data for real-world fintech company profiles
into data/test_tenants/<TENANT_ID>/
"""

import os
import csv
import json
import random
import hashlib
import hmac as _hmac
from datetime import datetime, timedelta, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_TENANTS_DIR = os.path.join(BASE_DIR, "test_tenants")
SALT = "dpdp_project_salt_2024"

# ── Reference Data ─────────────────────────────────────────────────────────────

EVENT_TYPES      = ["credit_check","loan_disbursal","emi_collection","kyc_verification",
                    "marketing_push","data_enrichment","account_update","fraud_check"]
EMPLOYEE_ROLES   = ["collections_agent","underwriter","customer_support",
                    "data_analyst","compliance_officer","engineer","manager"]
AUTHORISED_ROLES = {"compliance_officer","underwriter","data_analyst","manager"}
PII_CATEGORIES   = ["name","dob","pan","aadhaar","bank_account","address","phone","email"]
DATA_CATEGORIES  = ["kyc_documents","transaction_history","credit_score","contact_info","device_info"]
SYSTEM_TYPES     = ["crm","core_banking","analytics","kyc_platform","payment_gateway","data_warehouse"]
PURPOSES         = ["loan_processing","emi_collection","kyc_verification",
                    "credit_check","marketing","account_management","fraud_detection"]

ROLE_REASONS = {
    "collections_agent":  ["loan_review","support_query"],
    "underwriter":        ["loan_review","kyc_check","fraud_investigation"],
    "customer_support":   ["support_query","kyc_check"],
    "data_analyst":       ["data_export","fraud_investigation"],
    "compliance_officer": ["loan_review","kyc_check","fraud_investigation","data_export"],
    "engineer":           ["fraud_investigation","support_query"],
    "manager":            ["loan_review","kyc_check","fraud_investigation","data_export","support_query"],
}
ROLE_PII = {
    "collections_agent":  ["name","phone","bank_account"],
    "underwriter":        ["name","dob","pan","aadhaar","bank_account","address"],
    "customer_support":   ["name","phone","email"],
    "data_analyst":       ["dob","phone","email","bank_account"],
    "compliance_officer": ["name","dob","pan","aadhaar","bank_account","address","phone","email"],
    "engineer":           [],
    "manager":            ["name","phone","email"],
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def uid(prefix, n):
    return f"{prefix}-{str(n).zfill(4)}"

def h(raw_id: str, tenant_id: str) -> str:
    key = f"{SALT}:{tenant_id}".encode()
    return _hmac.new(key, raw_id.encode(), hashlib.sha256).hexdigest()[:12]

def rand_date(start_days_ago: int, end_days_ago: int = 0) -> date:
    start = date.today() - timedelta(days=start_days_ago)
    end   = date.today() - timedelta(days=end_days_ago)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))

def wc(choices, weights):
    return random.choices(choices, weights=weights, k=1)[0]

def write_csv(path: str, rows: list[dict]):
    if not rows:
        return
    fields = [k for k in rows[0].keys() if not k.startswith("_")]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: v for k, v in row.items() if not k.startswith("_")} for row in rows)


def generate_single_tenant(profile: dict):
    """
    Generate 10 schema-aligned CSVs + generation_report.txt for 1 tenant profile.
    """
    tenant_id   = profile["tenant_id"]
    tenant_name = profile["tenant_name"]
    n_customers = profile["n_customers"]
    seed_val    = profile["seed"]
    v_rates     = profile["violation_rates"]

    random.seed(seed_val)
    out_dir = os.path.join(TEST_TENANTS_DIR, tenant_id)
    os.makedirs(out_dir, exist_ok=True)

    seeding_log = {k: [] for k in v_rates}

    def seed_v(vtype: str, record_id: str, override_rate: float = None) -> bool:
        r = override_rate if override_rate is not None else v_rates.get(vtype, 0.0)
        triggered = random.random() < r
        if triggered and vtype in seeding_log:
            seeding_log[vtype].append(record_id)
        return triggered

    print(f"\n==================================================")
    print(f"Generating Tenant: {tenant_id} — {tenant_name}")
    print(f"==================================================")

    # 1. governance_config
    gov_rows = [{
        "tenant_id":                    tenant_id,
        "tenant_name":                  tenant_name,
        "grievance_endpoint_available": profile["grievance_endpoint"],
        "dpo_assigned":                 profile["dpo_assigned"],
        "dpo_contact_masked":           profile["dpo_contact"],
        "audit_frequency_days":         profile["audit_freq_days"],
        "last_audit_date":              rand_date(250, 90),
        "risk_level":                   profile["risk_level"],
    }]
    write_csv(os.path.join(out_dir, "governance_config.csv"), gov_rows)
    print("  [OK] governance_config.csv (1 row)")

    # 2. system_inventory
    sys_rows = []
    tp_hashes = []
    for i in range(1, 13):
        raw_id = uid("SYS", i)
        stype = random.choice(SYSTEM_TYPES)
        is_tp = random.random() < 0.45
        ptype = "third_party_processor" if is_tp else "internal"
        
        no_dpa = is_tp and seed_v("no_dpa", raw_id)
        dpa_signed = not no_dpa if is_tp else True
        dpa_expiry = None
        if dpa_signed and is_tp:
            dpa_expiry = date.today() + timedelta(days=random.randint(30, 365))

        sys_h = h(raw_id, tenant_id)
        if is_tp:
            tp_hashes.append(sys_h)

        no_enc = seed_v("no_encryption", raw_id)

        sys_rows.append({
            "system_hash":              sys_h,
            "tenant_id":               tenant_id,
            "system_name":             f"{stype.replace('_',' ').title()} System {i}",
            "system_type":             stype,
            "pii_stored":              random.random() < 0.75,
            "encryption_enabled":      not no_enc,
            "access_control_enabled":  random.random() > 0.05,
            "retention_policy_applied": random.random() > 0.10,
            "third_party_integrations": random.choice(["Experian","CIBIL","AWS","Salesforce","None"]),
            "data_processor_type":     ptype,
            "dpa_signed":              dpa_signed,
            "dpa_expiry_date":         dpa_expiry,
        })
    write_csv(os.path.join(out_dir, "system_inventory.csv"), sys_rows)
    print(f"  [OK] system_inventory.csv ({len(sys_rows)} rows)")

    # 3. policies
    policy_defs = [
        ("retention", "KYC Retention Policy", 1825, "days", True),
        ("retention", "Transaction History Retention", 2190, "days", True),
        ("consent", "Consent Expiry Policy", 365, "days", True),
        ("encryption", "Data Encryption Standard", None, None, True),
        ("access_control", "PII Access Control Policy", None, None, True),
        ("breach_notification", "Breach Notification SLA", 72, "hours", True),
    ]
    pol_rows = []
    for i, (ptype, pname, val, unit, active) in enumerate(policy_defs, 1):
        raw_id = uid("POL", i)
        eff = rand_date(730, 180)
        pol_rows.append({
            "policy_hash":          h(raw_id, tenant_id),
            "tenant_id":            tenant_id,
            "policy_type":          ptype,
            "policy_name":          pname,
            "policy_value_numeric": val,
            "policy_value_unit":    unit,
            "policy_value_text":    None,
            "effective_date":       eff,
            "last_updated":         eff,
            "is_active":            active,
        })
    write_csv(os.path.join(out_dir, "policies.csv"), pol_rows)
    print(f"  [OK] policies.csv ({len(pol_rows)} rows)")

    # 4. customer_master
    customers = []
    for i in range(1, n_customers + 1):
        raw_id   = uid("CUST", i)
        is_minor = random.random() < profile["minor_ratio"]
        kyc      = wc(["verified","pending","expired","rejected"], [0.85, 0.08, 0.04, 0.03])
        acc_st   = wc(["active","dormant","closed"], [0.75, 0.15, 0.10])
        country  = wc(["IN","US","AE"], [0.95, 0.03, 0.02])
        dp_type  = "minor" if is_minor else ("NRI" if country != "IN" else "individual")
        created  = rand_date(1000, 30)

        seed_v("data_accuracy_unverified", raw_id)

        customers.append({
            "_raw_id":             raw_id,
            "customer_hash":       h(raw_id, tenant_id),
            "tenant_id":           tenant_id,
            "is_minor":            is_minor,
            "data_principal_type": dp_type,
            "account_status":      acc_st,
            "kyc_status":          kyc,
            "country":             country,
            "created_at":          created,
        })
    write_csv(os.path.join(out_dir, "customer_master.csv"), customers)
    print(f"  [OK] customer_master.csv ({len(customers)} rows)")

    # 5. consent_records
    consent_rows = []
    cust_consents = {}
    con_counter = 1
    all_raw_con_ids = []

    for cust in customers:
        raw_cid   = cust["_raw_id"]
        c_hash    = cust["customer_hash"]
        acc_age   = (date.today() - cust["created_at"]).days
        cust_consents[raw_cid] = []

        n_c = 2 if random.random() < 0.25 else 1
        for _ in range(n_c):
            raw_con_id = uid("CON", con_counter)
            con_counter += 1
            all_raw_con_ids.append(raw_con_id)

            con_date = rand_date(acc_age, max(acc_age - 30, 1))
            expiry_date = con_date + timedelta(days=random.randint(180, 730))

            stale = seed_v("stale_consent_reuse", raw_con_id)
            if stale and expiry_date < date.today():
                c_status = "active"
            elif expiry_date < date.today():
                c_status = wc(["expired","revoked","withdrawn"], [0.70, 0.20, 0.10])
            else:
                c_status = "active"

            purpose    = random.choice(["loan_processing","kyc_verification","account_management","emi_collection"])
            no_notice  = seed_v("no_notice", raw_con_id)
            is_bundled = seed_v("bundled_consent", raw_con_id)
            channel    = wc(["app","web","branch","implicit","pre_ticked"], [0.45, 0.30, 0.15, 0.06, 0.04])
            if is_bundled:
                channel = random.choice(["implicit","pre_ticked"])

            notice = (not no_notice) if channel in ("implicit","pre_ticked") else True

            withdrawal_date = None
            if c_status == "withdrawn":
                withdrawal_date = max(expiry_date - timedelta(days=50), con_date + timedelta(days=1))

            needs_guardian = cust["is_minor"] and (not seed_v("minor_no_guardian", raw_con_id))

            consent_rows.append({
                "_raw_id":               raw_con_id,
                "_needs_guardian":       needs_guardian,
                "consent_hash":          h(raw_con_id, tenant_id),
                "customer_hash":         c_hash,
                "tenant_id":             tenant_id,
                "consent_status":        c_status,
                "consent_date":          con_date,
                "expiry_date":           expiry_date,
                "withdrawal_date":       withdrawal_date,
                "consented_purpose":     purpose,
                "consent_version":       "v2.0",
                "notice_provided":       notice,
                "is_bundled":            is_bundled,
                "consent_channel":       channel,
                "guardian_consent_hash": None,
            })
            cust_consents[raw_cid].append({
                "raw_id": raw_con_id,
                "hash":   h(raw_con_id, tenant_id),
                "purpose": purpose,
            })

    for row in consent_rows:
        if row["_needs_guardian"]:
            others = [cid for cid in all_raw_con_ids if cid != row["_raw_id"]]
            row["guardian_consent_hash"] = h(random.choice(others), tenant_id) if others else None

    write_csv(os.path.join(out_dir, "consent_records.csv"), consent_rows)
    print(f"  [OK] consent_records.csv ({len(consent_rows)} rows)")

    # 6. transaction_events
    tx_rows = []
    evt_counter = 1
    for cust in customers:
        raw_cid  = cust["_raw_id"]
        c_hash   = cust["customer_hash"]
        consents = cust_consents.get(raw_cid, [])
        if not consents:
            continue

        for _ in range(random.randint(1, 3)):
            raw_eid = uid("EVT", evt_counter)
            evt_counter += 1

            con      = random.choice(consents)
            evt_type = random.choice(EVENT_TYPES)
            mismatch = seed_v("purpose_mismatch", raw_eid)
            proc_purp = (random.choice([p for p in PURPOSES if p != con["purpose"]])
                         if mismatch else con["purpose"])

            is_tp = random.random() < 0.25
            if is_tp:
                seed_v("third_party_no_consent", raw_eid)

            is_cb = False
            country = None
            if is_tp:
                is_cb = random.random() < 0.25
                if is_cb:
                    country = wc(["US","AE","GB","SG"], [0.4, 0.3, 0.2, 0.1])
                    seed_v("cross_border_no_auth", raw_eid)

            tp_hash = random.choice(tp_hashes) if (is_tp and tp_hashes) else (tp_hashes[0] if tp_hashes else None)
            if is_tp and not tp_hash:
                is_tp = False

            tx_rows.append({
                "event_hash":              h(raw_eid, tenant_id),
                "customer_hash":           c_hash,
                "tenant_id":               tenant_id,
                "consent_hash":            con["hash"],
                "event_type":              evt_type,
                "processing_purpose":      proc_purp,
                "event_date":              rand_date(180, 1),
                "shared_with_third_party": is_tp,
                "third_party_hash":        tp_hash if is_tp else None,
                "is_cross_border":         is_cb,
                "transfer_country":        country,
            })
    write_csv(os.path.join(out_dir, "transaction_events.csv"), tx_rows)
    print(f"  [OK] transaction_events.csv ({len(tx_rows)} rows)")

    # 7. access_logs
    acc_rows = []
    for i in range(1, 100):
        raw_aid = uid("ACC", i)
        cust    = random.choice(customers)
        raw_emp = uid("EMP", random.randint(1, 15))
        unauth  = seed_v("unauthorised_access", raw_aid)

        role   = wc(["collections_agent","customer_support","engineer"], [0.50, 0.30, 0.20]) if unauth else random.choice(EMPLOYEE_ROLES)
        reason = random.choice(ROLE_REASONS[role])
        outcome = wc(["granted","denied"], [0.55, 0.45]) if unauth else "granted"

        pii_fields = [] if outcome == "denied" else (
            random.sample(PII_CATEGORIES, k=random.randint(1, 3)) if unauth
            else random.sample(ROLE_PII[role], k=random.randint(1, min(3, len(ROLE_PII[role])))) if ROLE_PII[role] else []
        )
        accessed = len(pii_fields) > 0
        pii_str  = ",".join(pii_fields) if accessed else None

        if accessed and set(pii_fields) - set(ROLE_PII.get(role, [])):
            seed_v("pii_over_collection", raw_aid)

        acc_rows.append({
            "access_hash":          h(raw_aid, tenant_id),
            "customer_hash":        cust["customer_hash"],
            "tenant_id":            tenant_id,
            "employee_hash":        h(raw_emp, tenant_id),
            "employee_role":        role,
            "accessed_pii":         accessed,
            "pii_fields_accessed":  pii_str,
            "access_reason":        reason,
            "access_outcome":       outcome,
            "data_volume_accessed": "medium" if accessed else "low",
            "access_date":          rand_date(180, 1),
        })
    write_csv(os.path.join(out_dir, "access_logs.csv"), acc_rows)
    print(f"  [OK] access_logs.csv ({len(acc_rows)} rows)")

    # 8. data_lifecycle
    lfc_rows = []
    lfc_counter = 1
    seen_cc = set()

    for cust in customers:
        c_hash = cust["customer_hash"]
        cats   = random.sample(DATA_CATEGORIES, k=random.randint(1, 2))
        for cat in cats:
            if (c_hash, cat) in seen_cc:
                continue
            seen_cc.add((c_hash, cat))

            raw_lid = uid("LFC", lfc_counter)
            lfc_counter += 1

            created = cust["created_at"]
            expiry  = created + timedelta(days=1825)

            overdue = seed_v("retention_overdue", raw_lid)
            if overdue:
                expiry   = date.today() - timedelta(days=random.randint(10, 200))
                r_status = "expired"
            else:
                r_status = "active" if expiry > date.today() else "expired"

            purpose_done = seed_v("purpose_complete_not_deleted", raw_lid)
            purpose_completed = True if purpose_done else random.random() < 0.15

            erasure_req = random.random() < 0.08
            legal_hold  = random.random() < 0.05
            erasure_date = rand_date(90, 5) if erasure_req else None

            lfc_rows.append({
                "lifecycle_hash":         h(raw_lid, tenant_id),
                "customer_hash":          c_hash,
                "tenant_id":              tenant_id,
                "data_category":          cat,
                "retention_expiry_date":  expiry,
                "retention_status":       r_status,
                "purpose_completed":      purpose_completed,
                "erasure_requested":      erasure_req,
                "erasure_date":           erasure_date,
                "legal_hold_flag":        legal_hold,
                "erasure_request_source": "user" if erasure_req else None,
            })
    write_csv(os.path.join(out_dir, "data_lifecycle.csv"), lfc_rows)
    print(f"  [OK] data_lifecycle.csv ({len(lfc_rows)} rows)")

    # 9. security_events
    sec_rows = []
    for i in range(1, 16):
        raw_sid = uid("SEC", i)
        cust    = random.choice(customers)

        breach     = random.random() < profile.get("breach_rate", 0.20)
        b_date     = None
        delay_hrs  = None

        if breach:
            b_date    = rand_date(300, 10)
            delayed   = seed_v("breach_delay", raw_sid)
            delay_hrs = random.randint(73, 240) if delayed else random.randint(2, 48)

        no_enc = seed_v("no_encryption", raw_sid)
        if no_enc:
            pii_enc  = False
            enc_type = wc(["none","md5"], [0.60, 0.40])
        else:
            pii_enc  = True
            enc_type = wc(["AES-256","AES-128","RSA-2048"], [0.65, 0.25, 0.10])

        sec_rows.append({
            "security_hash":            h(raw_sid, tenant_id),
            "customer_hash":            cust["customer_hash"],
            "tenant_id":                tenant_id,
            "pii_encrypted":            pii_enc,
            "encryption_type":          enc_type,
            "breach_detected":          breach,
            "breach_confirmed_date":    b_date,
            "notification_delay_hours": delay_hrs,
            "affected_user_count":      "moderate" if breach else None,
            "data_categories_breached": "name,phone" if breach else None,
            "security_audit_flag":      random.random() < 0.30,
        })
    write_csv(os.path.join(out_dir, "security_events.csv"), sec_rows)
    print(f"  [OK] security_events.csv ({len(sec_rows)} rows)")

    # 10. dsar_requests
    dsar_rows = []
    active_custs = [c for c in customers if c["account_status"] == "active"]
    dsar_sample  = random.sample(active_custs, k=min(15, len(active_custs)))

    for i, cust in enumerate(dsar_sample, 1):
        raw_did   = uid("DSAR", i)
        sub_date  = rand_date(300, 5)
        sla_due   = sub_date + timedelta(days=30)
        sla_br    = seed_v("dsar_sla_breach", raw_did)

        if sla_br:
            fulfilled = None if random.random() < 0.40 else sub_date + timedelta(days=random.randint(31, 75))
            f_status  = "pending" if fulfilled is None else "fulfilled"
        else:
            fulfilled = sub_date + timedelta(days=random.randint(1, 25))
            f_status  = "fulfilled"

        dsar_rows.append({
            "dsar_hash":          h(raw_did, tenant_id),
            "customer_hash":      cust["customer_hash"],
            "tenant_id":          tenant_id,
            "request_type":       wc(["erasure","access","correction","nomination"], [0.45, 0.30, 0.20, 0.05]),
            "submitted_date":     sub_date,
            "acknowledged_date":  sub_date + timedelta(days=1),
            "sla_due_date":       sla_due,
            "sla_breached":       sla_br,
            "fulfilled_date":     fulfilled,
            "fulfillment_status": f_status,
            "rejection_reason":   None,
        })
    write_csv(os.path.join(out_dir, "dsar_requests.csv"), dsar_rows)
    print(f"  [OK] dsar_requests.csv ({len(dsar_rows)} rows)")

    # Ground-truth Report
    report_lines = [
        "=" * 60,
        f"DPDP SYNTHETIC TEST TENANT — GENERATION REPORT",
        f"Tenant : {tenant_id} — {tenant_name}",
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 60, "",
        "SEEDED VIOLATIONS GROUND TRUTH:",
        "-" * 40,
    ]
    tot = 0
    for vtype, recs in seeding_log.items():
        n = len(recs)
        tot += n
        report_lines.append(f"  {vtype:<32} n={n}")
    report_lines.append(f"\nTOTAL SEEDED VIOLATIONS: {tot}\n")

    with open(os.path.join(out_dir, "generation_report.txt"), "w") as f:
        f.write("\n".join(report_lines))

    print(f"  [OK] generation_report.txt (Total seeded violations: {tot})")
    print(f"SUCCESS: Created 10 schema CSVs in data/test_tenants/{tenant_id}/\n")


# ── ALL 5 REAL-WORLD FINTECH PROFILES ──────────────────────────────────────────

ALL_PROFILES = [
    {
        "tenant_id":        "QUICKLOAN-001",
        "tenant_name":      "QuickLoan Instant Credits Pvt Ltd",
        "n_customers":      60,
        "seed":             101,
        "minor_ratio":      0.02,
        "dpo_assigned":     False,
        "grievance_endpoint": False,
        "dpo_contact":      None,
        "audit_freq_days":  180,
        "risk_level":       "HIGH",
        "breach_rate":      0.30,
        "violation_rates": {
            "stale_consent_reuse":         0.35,
            "no_notice":                   0.25,
            "bundled_consent":             0.20,
            "minor_no_guardian":           0.00,
            "purpose_mismatch":            0.30,
            "third_party_no_consent":      0.25,
            "cross_border_no_auth":        0.15,
            "unauthorised_access":         0.20,
            "pii_over_collection":         0.25,
            "retention_overdue":           0.40,
            "purpose_complete_not_deleted": 0.35,
            "no_encryption":               0.45,
            "breach_delay":                0.35,
            "no_dpa":                      0.40,
            "dsar_sla_breach":             0.30,
            "data_accuracy_unverified":    0.20,
        }
    },
    {
        "tenant_id":        "PAYFLEX-002",
        "tenant_name":      "PayFlex BNPL Solutions India Pvt Ltd",
        "n_customers":      120,
        "seed":             202,
        "minor_ratio":      0.01,
        "dpo_assigned":     True,
        "grievance_endpoint": True,
        "dpo_contact":      "c***@payflex.in",
        "audit_freq_days":  90,
        "risk_level":       "MEDIUM",
        "breach_rate":      0.15,
        "violation_rates": {
            "stale_consent_reuse":         0.10,
            "no_notice":                   0.08,
            "bundled_consent":             0.30,
            "minor_no_guardian":           0.00,
            "purpose_mismatch":            0.15,
            "third_party_no_consent":      0.20,
            "cross_border_no_auth":        0.10,
            "unauthorised_access":         0.05,
            "pii_over_collection":         0.10,
            "retention_overdue":           0.15,
            "purpose_complete_not_deleted": 0.20,
            "no_encryption":               0.08,
            "breach_delay":                0.10,
            "no_dpa":                      0.45,
            "dsar_sla_breach":             0.15,
            "data_accuracy_unverified":    0.10,
        }
    },
    {
        "tenant_id":        "WEALTHNEST-003",
        "tenant_name":      "WealthNest Robo-Advisor & Investment Pvt Ltd",
        "n_customers":      200,
        "seed":             303,
        "minor_ratio":      0.00,
        "dpo_assigned":     True,
        "grievance_endpoint": True,
        "dpo_contact":      "d***@wealthnest.in",
        "audit_freq_days":  30,
        "risk_level":       "LOW",
        "breach_rate":      0.02,
        "violation_rates": {
            "stale_consent_reuse":         0.02,
            "no_notice":                   0.01,
            "bundled_consent":             0.02,
            "minor_no_guardian":           0.00,
            "purpose_mismatch":            0.03,
            "third_party_no_consent":      0.02,
            "cross_border_no_auth":        0.00,
            "unauthorised_access":         0.01,
            "pii_over_collection":         0.02,
            "retention_overdue":           0.03,
            "purpose_complete_not_deleted": 0.04,
            "no_encryption":               0.00,
            "breach_delay":                0.00,
            "no_dpa":                      0.02,
            "dsar_sla_breach":             0.02,
            "data_accuracy_unverified":    0.02,
        }
    },
    {
        "tenant_id":        "RURALCRED-004",
        "tenant_name":      "RuralCred Microfinance Access Pvt Ltd",
        "n_customers":      90,
        "seed":             404,
        "minor_ratio":      0.06,
        "dpo_assigned":     False,
        "grievance_endpoint": False,
        "dpo_contact":      None,
        "audit_freq_days":  180,
        "risk_level":       "CRITICAL",
        "breach_rate":      0.45,
        "violation_rates": {
            "stale_consent_reuse":         0.45,
            "no_notice":                   0.35,
            "bundled_consent":             0.40,
            "minor_no_guardian":           0.50,
            "purpose_mismatch":            0.40,
            "third_party_no_consent":      0.45,
            "cross_border_no_auth":        0.30,
            "unauthorised_access":         0.35,
            "pii_over_collection":         0.40,
            "retention_overdue":           0.50,
            "purpose_complete_not_deleted": 0.45,
            "no_encryption":               0.55,
            "breach_delay":                0.60,
            "no_dpa":                      0.50,
            "dsar_sla_breach":             0.45,
            "data_accuracy_unverified":    0.35,
        }
    },
    {
        "tenant_id":        "NEXUSNEOBANK-005",
        "tenant_name":      "Nexus Digital Bank & Financial Technologies Pvt Ltd",
        "n_customers":      250,
        "seed":             505,
        "minor_ratio":      0.00,
        "dpo_assigned":     True,
        "grievance_endpoint": True,
        "dpo_contact":      "d***@nexusneobank.in",
        "audit_freq_days":  30,
        "risk_level":       "LOW",
        "breach_rate":      0.00,
        "violation_rates": {
            "stale_consent_reuse":         0.00,
            "no_notice":                   0.00,
            "bundled_consent":             0.00,
            "minor_no_guardian":           0.00,
            "purpose_mismatch":            0.00,
            "third_party_no_consent":      0.00,
            "cross_border_no_auth":        0.00,
            "unauthorised_access":         0.00,
            "pii_over_collection":         0.00,
            "retention_overdue":           0.00,
            "purpose_complete_not_deleted": 0.00,
            "no_encryption":               0.00,
            "breach_delay":                0.00,
            "no_dpa":                      0.00,
            "dsar_sla_breach":             0.00,
            "data_accuracy_unverified":    0.00,
        }
    }
]


if __name__ == "__main__":
    print("Generating all 5 test tenant CSV datasets...")
    for p in ALL_PROFILES:
        generate_single_tenant(p)
    print("All 5 test tenant datasets successfully generated in data/test_tenants/!")
