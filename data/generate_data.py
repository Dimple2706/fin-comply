"""
[DEPRECATED] generate_data.py — DO NOT USE FOR NEW DATA GENERATION
====================================================================
This file is retained for historical reference only.

Why it was deprecated (E-09):
  - Outputs raw un-hashed IDs (consent_id, customer_id, event_id) instead of
    pre-hashed values, causing field name mismatches with the anonymization pipeline.
  - Generates phantom guardian_consent_id values (e.g. 'GC-<uuid>') that do not
    reference any real consent row, creating FK orphans that trigger false DPDP-005
    violations.
  - Third-party FK references are not validated against system_inventory, producing
    dangling references that the old db_writer silently patched with fake rows.
  - Non-deterministic for many fields — same profile produces different violation
    counts on each run, making ML training non-reproducible.

Canonical replacement:
  USE data/generate_test_tenants.py instead.
  - Outputs pre-hashed field values matching the anonymization pipeline schema.
  - Guarantees FK integrity: consent_records are generated before transaction_events,
    guardian_consent_hash references real consent IDs from the same run.
  - Deterministic: each tenant profile has a fixed seed, same profile = same CSVs.
  - Covers all 5 test tenants: QUICKLOAN-001, PAYFLEX-002, WEALTHNEST-003,
    RURALCRED-004, NEXUSNEOBANK-005.

Usage:
    python -m data.generate_test_tenants      (from project root)
    python data/generate_test_tenants.py      (from project root)
"""

import json
import os
import sys
import uuid
import random
import shutil
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg
import dotenv

dotenv.load_dotenv()

# â”€â”€ Resolve project root â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SCRIPT_DIR = Path(__file__).resolve().parent          # data/
PROJECT_ROOT = SCRIPT_DIR.parent                      # capstone_f/
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import tenant_raw_dir
from src.anonymization.pipeline import run_anonymization_pipeline
from src.agent_layer.orchestrator import run_compliance_analysis

# â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CONFIG_PATH = SCRIPT_DIR / "generator_config.json"
RAW_SYNTHETIC_DIR = SCRIPT_DIR / "raw_synthetic"
REPORT_PATH = PROJECT_ROOT / "generation_report.txt"

# â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
AUTHORISED_ROLES = {"compliance_officer", "underwriter", "data_analyst", "manager"}

SYSTEM_TYPES = ["crm", "core_banking", "analytics", "kyc_platform", "payment_gateway", "data_warehouse"]
SYSTEM_NAMES = [
    "Core Banking System", "CRM Platform", "Analytics Engine",
    "KYC Platform", "Payment Gateway", "Data Warehouse",
    "Fraud Detection System", "Loan Origination System",
    "Customer Portal", "Reporting Engine", "Mobile Banking",
    "Transaction Monitor"
]
DATA_TYPES_STORED = ["customer_data", "transaction_data", "kyc_documents", "credit_scores", "payment_records"]

POLICY_NAMES = {
    "retention": "Data Retention Policy",
    "consent": "Consent Management Policy",
    "encryption": "Encryption Standards Policy",
    "access_control": "Access Control Policy",
    "breach_notification": "Breach Notification Policy",
    "data_minimisation": "Data Minimisation Policy",
}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _uid() -> str:
    """Short unique ID for CSV identifiers."""
    return uuid.uuid4().hex[:12]


def _pick(dist: Any) -> Any:
    """
    Resolve a value from a config entry.
    - If it's a dict with string keys summing to ~1.0, treat as probability distribution.
    - If it's a dict with 'true'/'false' keys, return bool.
    - Otherwise return as-is (fixed value).
    """
    if isinstance(dist, dict):
        keys = list(dist.keys())
        weights = list(dist.values())
        # Normalise weights to handle float imprecision
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]
        chosen = random.choices(keys, weights=weights, k=1)[0]
        # Convert "true"/"false" strings to booleans
        if chosen == "true":
            return True
        if chosen == "false":
            return False
        return chosen
    return dist


def _pick_bool(dist: Any, default: bool = False) -> bool:
    """Pick a boolean value from a distribution or fixed value."""
    val = _pick(dist) if isinstance(dist, dict) else dist
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return default


def _random_date(start_year: int = 2024, end_year: int = 2026) -> str:
    """Random ISO date string."""
    start = date(start_year, 1, 1)
    end = date(end_year, 6, 30)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, max(delta, 1)))).isoformat()


def _random_past_date() -> str:
    """Random date in the past 2 years."""
    return _random_date(2024, 2026)


def _random_future_date() -> str:
    """Random date 1-2 years ahead."""
    return _random_date(2026, 2028)


def _random_timestamp(base_date: str = None) -> str:
    """ISO timestamp for a date."""
    if base_date:
        return f"{base_date}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"
    return f"{_random_past_date()}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"


def _get_db_connection():
    """Direct psycopg3 connection matching the project's DB pattern."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "tenant_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
    )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CSV GENERATORS â€” one per table, in FK dependency order
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def generate_governance_config(profile: dict) -> List[dict]:
    """Generate exactly 1 governance_config row."""
    fd = profile["field_distributions"].get("governance_config", {})
    tenant_id = profile["tenant_id"]

    dpo_assigned = _pick_bool(fd.get("dpo_assigned", True))
    # Required whenever a DPO is assigned -- was never generated at all, so
    # ingestion rejected any profile with dpo_assigned=True. field_mapper.py
    # reads the raw column as "dpo_contact" (or pre-masked "dpo_contact_masked"),
    # not "dpo_contact_email" -- that name is only field_config.json's
    # documentation label for the semantic field, not the actual CSV header.
    dpo_contact_email = f"dpo@{tenant_id.lower()}.example" if dpo_assigned else ""

    return [{
        "tenant_id": tenant_id,
        "tenant_name": profile.get("profile_name", tenant_id),
        "grievance_endpoint_available": _pick_bool(fd.get("grievance_endpoint_available", True)),
        "dpo_assigned": dpo_assigned,
        "dpo_contact": dpo_contact_email,
        "audit_frequency_days": fd.get("audit_frequency_days", 90),
        "last_audit_date": fd.get("last_audit_date", _random_past_date()),
        "risk_level": fd.get("risk_level", "MEDIUM"),
    }]


def generate_customer_master(profile: dict) -> List[dict]:
    """Generate customer_master rows. Returns rows + collected customer_ids."""
    n = profile["record_counts"]["n_customers"]
    fd = profile["field_distributions"].get("customer_master", {})
    tenant_id = profile["tenant_id"]
    rows = []

    for i in range(n):
        cust_id = f"CUST-{tenant_id}-{_uid()}"
        is_minor_dist = fd.get("is_minor", False)
        is_minor = _pick_bool(is_minor_dist)

        if is_minor:
            data_principal_type = fd.get("data_principal_type_when_minor", "minor")
        else:
            data_principal_type = fd.get("data_principal_type_when_adult",
                                         fd.get("data_principal_type", "individual"))

        account_status = _pick(fd.get("account_status", "active"))
        kyc_status = _pick(fd.get("kyc_status", "verified"))

        # Generate DOB consistent with is_minor
        if is_minor:
            # Age 10-17
            birth_year = date.today().year - random.randint(10, 17)
        else:
            birth_year = date.today().year - random.randint(18, 65)
        dob = date(birth_year, random.randint(1, 12), random.randint(1, 28)).isoformat()

        additional_attributes = json.dumps({"data_accuracy_verified": True})

        rows.append({
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "is_minor": is_minor,
            "data_principal_type": data_principal_type,
            "account_status": account_status,
            "kyc_status": kyc_status,
            "country": "IN",
            "created_at": _random_past_date(),
            "dob": dob,
            "additional_attributes": additional_attributes,
        })
    return rows


def generate_consent_records(profile: dict, customer_rows: List[dict]) -> List[dict]:
    """Generate consent_records using customer_ids from customer_master."""
    n = profile["record_counts"]["n_consent_records"]
    fd = profile["field_distributions"].get("consent_records", {})
    tenant_id = profile["tenant_id"]

    customer_ids = [r["customer_id"] for r in customer_rows]
    minor_customer_ids = {r["customer_id"] for r in customer_rows if r["is_minor"]}

    rows = []
    guardian_rows = []
    for i in range(n):
        consent_id = f"CON-{tenant_id}-{_uid()}"
        cust_id = random.choice(customer_ids)
        is_minor_customer = cust_id in minor_customer_ids

        # Consent status â€” may differ for minors
        if is_minor_customer and "minor_rows_consent_status" in fd:
            consent_status = _pick(fd["minor_rows_consent_status"])
        elif not is_minor_customer and "non_minor_rows_consent_status" in fd:
            consent_status = _pick(fd["non_minor_rows_consent_status"])
        else:
            consent_status = _pick(fd.get("consent_status", "active"))

        notice_provided = _pick_bool(fd.get("notice_provided", True))
        is_bundled = _pick_bool(fd.get("is_bundled", False))
        consent_channel = _pick(fd.get("consent_channel", "app"))

        consented_purpose = _pick(fd.get("consented_purpose", "loan_processing"))

        # Consent version â€” some profiles have outdated versions
        outdated_pct = fd.get("consent_version_outdated_pct", 0)
        if isinstance(outdated_pct, (int, float)) and random.random() < outdated_pct:
            consent_version = "v0.1-legacy"
        else:
            consent_version = "v2.0"

        # Consent timestamp and expiry. DB constraint chk_expiry_after_consent
        # requires expiry strictly after consent -- independently sampling
        # from "past" (2024-2026-06) and "future" (2026-2028-06) ranges lets
        # them overlap in 2026 and frequently produced expiry < consent.
        # Anchor expiry to consent + 1-2 years instead.
        consent_ts = _random_timestamp()
        consent_date_val = date.fromisoformat(consent_ts.split("T")[0])
        expiry_date_val = consent_date_val + timedelta(days=random.randint(365, 730))
        expiry_ts = _random_timestamp(expiry_date_val.isoformat())

        # Withdrawal timestamp â€” only if status is withdrawn (chk_withdrawal_status)
        withdrawal_ts = ""
        if consent_status == "withdrawn":
            withdrawal_ts = _random_timestamp(consent_ts.split("T")[0])

        # Guardian consent hash â€” handle minor-specific logic
        guardian_consent_id = ""
        if is_minor_customer:
            null_pct = fd.get("minor_rows_guardian_consent_hash_null_pct", 1.0)
            gh_val = fd.get("minor_rows_guardian_consent_hash",
                           fd.get("guardian_consent_hash", "null"))
            if gh_val == "null" or (isinstance(null_pct, (int, float)) and random.random() < null_pct):
                # No valid guardian consent on file -- intentional, for
                # profiles designed to be non-compliant on DPDP-005.
                guardian_consent_id = ""
            else:
                # Create a REAL guardian consent record and reference its
                # consent_id, rather than a phantom ID matching no row.
                # DPDP-005 evaluation resolves guardian consent by joining
                # this value against another consent_records row's
                # consent_id -- a fabricated ID that matches nothing left
                # every minor showing as a violation regardless of the
                # profile's intended compliance level.
                guardian_consent_id = f"CON-{tenant_id}-{_uid()}"
                guardian_rows.append({
                    "consent_id": guardian_consent_id,
                    "customer_id": cust_id,
                    "tenant_id": tenant_id,
                    "consent_status": "active",
                    "consent_timestamp": _random_timestamp(),
                    "expiry_timestamp": _random_timestamp(_random_future_date()),
                    "consented_purpose": "guardian_authorization",
                    "consent_version": "v2.0",
                    "notice_provided": True,
                    "is_bundled": False,
                    "consent_channel": _pick(fd.get("consent_channel", "app")),
                    "withdrawal_timestamp": "",
                    "guardian_consent_id": "",
                    "additional_attributes": "{}",
                })
        else:
            gh_val = fd.get("non_minor_rows_guardian_consent_hash",
                           fd.get("guardian_consent_hash", "null"))
            if gh_val != "null":
                guardian_consent_id = f"GC-{_uid()}"

        rows.append({
            "consent_id": consent_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "consent_status": consent_status,
            "consent_timestamp": consent_ts,
            "expiry_timestamp": expiry_ts,
            "consented_purpose": consented_purpose,
            "consent_version": consent_version,
            "notice_provided": notice_provided,
            "is_bundled": is_bundled,
            "consent_channel": consent_channel,
            "withdrawal_timestamp": withdrawal_ts,
            "guardian_consent_id": guardian_consent_id,
            "additional_attributes": "{}",
        })
    rows.extend(guardian_rows)
    return rows


def generate_transaction_events(profile: dict, consent_rows: List[dict], system_rows: List[dict]) -> List[dict]:
    """Generate transaction_events using consent_ids from consent_records."""
    n = profile["record_counts"]["n_transaction_events"]
    fd = profile["field_distributions"].get("transaction_events", {})
    tenant_id = profile["tenant_id"]

    consent_data = [
        (r["consent_id"], r["customer_id"], r["consented_purpose"], r["consent_timestamp"], r["expiry_timestamp"])
        for r in consent_rows
    ]

    # Third-party FK integrity (matches the fix already prescribed for the
    # canonical generator): only external systems can be a real third-party
    # recipient. A fabricated ID that matches no system_inventory row fails
    # cross-file validation at ingestion.
    third_party_system_ids = [s["system_id"] for s in system_rows if s.get("data_processor_type") != "internal"]

    mismatch_pct = fd.get("consented_purpose_mismatch_pct", 0)

    rows = []
    for i in range(n):
        event_id = f"EVT-{tenant_id}-{_uid()}"
        consent_id, cust_id, consented_purpose, consent_ts_val, expiry_ts_val = random.choice(consent_data)

        event_type = _pick(fd.get("event_type", "credit_check"))

        # Purpose mismatch logic
        if isinstance(mismatch_pct, (int, float)) and random.random() < mismatch_pct:
            # Deliberately pick a DIFFERENT purpose from consented
            mismatch_purposes = [
                p for p in ["marketing", "data_enrichment", "credit_check", "fraud_detection"]
                if p != consented_purpose
            ]
            processing_purpose = random.choice(mismatch_purposes) if mismatch_purposes else "marketing"
        else:
            # Not a deliberate mismatch -- processing_purpose must actually
            # equal the linked consent's purpose. Independently re-sampling
            # from a "processing_purpose" distribution (even one identical
            # to the consented-purpose distribution) produces an accidental
            # mismatch on every draw that lands on a different value,
            # firing DPDP-002 on data that was never meant to violate it.
            processing_purpose = consented_purpose

        shared = _pick_bool(fd.get("shared_with_third_party", False))
        is_cross_border = _pick_bool(fd.get("is_cross_border", False))

        third_party_id = ""
        if shared:
            if third_party_system_ids:
                third_party_id = random.choice(third_party_system_ids)
            else:
                # No real external system exists for this tenant to share
                # with -- don't fabricate a reference to nothing.
                shared = False

        transfer_country = ""
        if is_cross_border:
            transfer_country = fd.get("transfer_country_for_cross_border", "US")

        # DPDP-001 fires when a transaction's timestamp falls after its own
        # consent's expiry date. Sampling the event timestamp fully
        # independently of which consent it's linked to let this happen by
        # pure chance even for consent_status='active' rows. Default to a
        # timestamp inside the consent's own valid window; genuine DPDP-001
        # violations still fire correctly via consent_status
        # (expired/withdrawn/revoked), independent of this.
        try:
            consent_dt = date.fromisoformat(str(consent_ts_val).split("T")[0])
            expiry_dt = date.fromisoformat(str(expiry_ts_val).split("T")[0])
            if expiry_dt > consent_dt:
                event_date_val = consent_dt + timedelta(days=random.randint(0, (expiry_dt - consent_dt).days))
                event_timestamp = f"{event_date_val.isoformat()}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"
            else:
                event_timestamp = consent_ts_val
        except (TypeError, ValueError):
            event_timestamp = _random_timestamp()

        rows.append({
            "event_id": event_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "consent_id": consent_id,
            "event_type": event_type,
            "processing_purpose": processing_purpose,
            "timestamp": event_timestamp,
            "shared_with_third_party": shared,
            "third_party_id": third_party_id,
            "is_cross_border": is_cross_border,
            "transfer_country": transfer_country,
            "additional_attributes": "{}",
        })
    return rows


def generate_access_logs(profile: dict, customer_rows: List[dict]) -> List[dict]:
    """Generate access_logs using customer_ids from customer_master."""
    n = profile["record_counts"]["n_access_logs"]
    fd = profile["field_distributions"].get("access_logs", {})
    tenant_id = profile["tenant_id"]

    customer_ids = [r["customer_id"] for r in customer_rows]
    unauthorised_pct = fd.get("unauthorised_role_pct", 0)

    rows = []
    for i in range(n):
        access_id = f"ACC-{tenant_id}-{_uid()}"
        cust_id = random.choice(customer_ids)
        employee_id = f"EMP-{_uid()}"

        is_unauthorised = isinstance(unauthorised_pct, (int, float)) and random.random() < unauthorised_pct

        if is_unauthorised:
            role_dist = fd.get("unauthorised_roles", {"customer_support": 0.50, "collections_agent": 0.30, "engineer": 0.20})
            employee_role = _pick(role_dist)
            accessed_pii = _pick_bool(fd.get("accessed_pii_when_unauthorised", True))
            dv_dist = fd.get("data_volume_accessed_when_unauthorised", {"low": 0.70, "medium": 0.20, "high": 0.10})
            data_volume = _pick(dv_dist)
        else:
            role_dist = fd.get("authorised_roles", fd.get("employee_role", {"compliance_officer": 0.30, "underwriter": 0.30, "data_analyst": 0.30, "manager": 0.10}))
            employee_role = _pick(role_dist)
            accessed_pii = _pick_bool(fd.get("accessed_pii_when_authorised", fd.get("accessed_pii", {"true": 0.40, "false": 0.60})))
            dv_dist = fd.get("data_volume_accessed_when_authorised", fd.get("data_volume_accessed", {"low": 0.70, "medium": 0.20, "high": 0.10}))
            data_volume = _pick(dv_dist)

        access_reason = _pick(fd.get("access_reason", "support_query"))
        access_outcome = _pick(fd.get("access_outcome", "granted"))

        # Enforce chk_denied_no_pii
        if access_outcome == "denied":
            accessed_pii = False

        pii_fields = "name,email,phone" if accessed_pii else ""

        # additional_attributes for unauthorised high/bulk PII access
        add_attr = "{}"
        if (employee_role not in AUTHORISED_ROLES
                and accessed_pii
                and data_volume in ("high", "bulk")):
            add_attr = json.dumps({"pii_fields_justified": False})

        rows.append({
            "access_id": access_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "employee_role": employee_role,
            "accessed_pii": accessed_pii,
            "pii_fields_accessed": pii_fields,
            "access_reason": access_reason,
            "access_outcome": access_outcome,
            "data_volume_accessed": data_volume,
            "timestamp": _random_timestamp(),
            "additional_attributes": add_attr,
        })
    return rows


def generate_data_lifecycle(profile: dict, customer_rows: List[dict]) -> List[dict]:
    """Generate data_lifecycle using customer_ids from customer_master."""
    n = profile["record_counts"]["n_data_lifecycle"]
    fd = profile["field_distributions"].get("data_lifecycle", {})
    tenant_id = profile["tenant_id"]

    customer_ids = [r["customer_id"] for r in customer_rows]

    past_pct = fd.get("retention_expiry_date_past_for_pct", 0)
    past_value = fd.get("retention_expiry_date_past_value", "2023-01-01")
    past_status = fd.get("retention_status_for_past", "expired")
    current_status_dist = fd.get("retention_status_for_current", fd.get("retention_status", {"active": 0.90, "pending_deletion": 0.10}))

    purpose_completed_pct = fd.get("purpose_completed_pct", 0)
    retention_when_complete = fd.get("retention_status_when_purpose_complete", None)

    rows = []
    used_pairs = set()  # DB: UNIQUE(customer_hash, data_category) per tenant
    for i in range(n):
        lifecycle_id = f"LC-{tenant_id}-{_uid()}"

        # A customer can have at most one lifecycle row per data_category.
        # Retry on collision instead of letting a duplicate reach the DB;
        # skip this row (rather than fabricate a workaround) if no free
        # pair can be found after a reasonable number of attempts.
        cust_id = None
        data_category = None
        for _attempt in range(20):
            candidate_cust = random.choice(customer_ids)
            candidate_category = _pick(fd.get("data_category", "kyc_documents"))
            if (candidate_cust, candidate_category) not in used_pairs:
                cust_id = candidate_cust
                data_category = candidate_category
                break
        if cust_id is None:
            continue
        used_pairs.add((cust_id, data_category))

        # Determine if this row has a past expiry date
        is_past = isinstance(past_pct, (int, float)) and random.random() < past_pct

        if is_past:
            retention_expiry_date = past_value
            retention_status = past_status
        else:
            # _random_future_date() samples a fixed 2026-2028 range, which
            # can land before today's actual date and make a "not past" row
            # look already-expired by accident (the same overlapping-range
            # bug already fixed for consent/expiry timestamps). Anchor to
            # today instead so "not past" is always genuinely future.
            retention_expiry_date = (date.today() + timedelta(days=random.randint(30, 730))).isoformat()
            retention_status = _pick(current_status_dist)

        # Purpose completed logic
        purpose_completed_dist = fd.get("purpose_completed", {"false": 0.90, "true": 0.10})
        if isinstance(purpose_completed_pct, (int, float)) and purpose_completed_pct > 0:
            purpose_completed = random.random() < purpose_completed_pct
        else:
            purpose_completed = _pick_bool(purpose_completed_dist)

        # Override retention status when purpose is complete (data_hoarder pattern)
        if purpose_completed and retention_when_complete:
            retention_status = retention_when_complete

        erasure_requested = _pick_bool(fd.get("erasure_requested", False))
        legal_hold_flag = _pick_bool(fd.get("legal_hold_flag", False))

        erasure_ts = ""
        erasure_source = ""
        if erasure_requested:
            erasure_ts = _random_timestamp(_random_past_date())
            erasure_source = "user"

        # DB constraint chk_expired_not_future: retention_status IN
        # ('expired','pending_deletion','deleted') requires
        # retention_expiry_date <= CURRENT_DATE. Any of these three can end
        # up paired with a future date here (via current_status_dist or the
        # purpose-complete override) -- keep the date consistent with the
        # final status rather than fighting it, so the profile's intended
        # status rate is preserved.
        if retention_status in ("expired", "pending_deletion", "deleted") and date.fromisoformat(retention_expiry_date) > date.today():
            retention_expiry_date = past_value

        rows.append({
            "lifecycle_id": lifecycle_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "data_category": data_category,
            "retention_expiry_date": retention_expiry_date,
            "retention_status": retention_status,
            "purpose_completed": purpose_completed,
            "erasure_requested": erasure_requested,
            "erasure_timestamp": erasure_ts,
            "legal_hold_flag": legal_hold_flag,
            "erasure_request_source": erasure_source,
            "additional_attributes": "{}",
        })
    return rows


def generate_security_events(profile: dict, customer_rows: List[dict]) -> List[dict]:
    """Generate security_events using customer_ids from customer_master."""
    n = profile["record_counts"]["n_security_events"]
    fd = profile["field_distributions"].get("security_events", {})
    tenant_id = profile["tenant_id"]

    customer_ids = [r["customer_id"] for r in customer_rows]

    breach_dist = fd.get("breach_detected", False)
    breach_rows_cfg = fd.get("breach_rows", {})
    non_breach_rows_cfg = fd.get("non_breach_rows", {})

    rows = []
    for i in range(n):
        sec_id = f"SEC-{tenant_id}-{_uid()}"
        cust_id = random.choice(customer_ids)

        breach_detected = _pick_bool(breach_dist)

        if breach_detected:
            pii_encrypted = _pick_bool(breach_rows_cfg.get("pii_encrypted", fd.get("pii_encrypted", True)))
            notification_delay = breach_rows_cfg.get("notification_delay_hours", 100)
            affected_user_count = breach_rows_cfg.get("affected_user_count", 100)
            breach_confirmed_at = _random_timestamp(_random_past_date())
            data_categories_breached = "kyc_documents,contact_info"
        else:
            pii_encrypted = _pick_bool(non_breach_rows_cfg.get("pii_encrypted", fd.get("pii_encrypted", True)))
            notification_delay = ""
            affected_user_count = ""
            breach_confirmed_at = ""
            data_categories_breached = ""

        # Encryption type depends on pii_encrypted (DB constraint)
        if pii_encrypted:
            enc_type_key = "encryption_type_when_encrypted_true"
            enc_type = breach_rows_cfg.get(enc_type_key, non_breach_rows_cfg.get(enc_type_key, fd.get(enc_type_key, "AES-256")))
            if isinstance(enc_type, dict):
                encryption_type = _pick(enc_type)
            else:
                encryption_type = enc_type
        else:
            enc_type_key = "encryption_type_when_encrypted_false"
            enc_type = breach_rows_cfg.get(enc_type_key, non_breach_rows_cfg.get(enc_type_key, fd.get(enc_type_key, "none")))
            if isinstance(enc_type, dict):
                encryption_type = _pick(enc_type)
            else:
                encryption_type = enc_type

        security_audit_flag = False

        rows.append({
            "security_id": sec_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "pii_encrypted": pii_encrypted,
            "encryption_type": encryption_type,
            "breach_detected": breach_detected,
            "breach_confirmed_at": breach_confirmed_at,
            "notification_delay_hours": notification_delay,
            "affected_user_count": affected_user_count,
            "data_categories_breached": data_categories_breached,
            "security_audit_flag": security_audit_flag,
            "additional_attributes": "{}",
        })
    return rows


def generate_dsar_requests(profile: dict, customer_rows: List[dict]) -> List[dict]:
    """Generate dsar_requests using customer_ids from customer_master."""
    n = profile["record_counts"]["n_dsar_requests"]
    fd = profile["field_distributions"].get("dsar_requests", {})
    tenant_id = profile["tenant_id"]

    customer_ids = [r["customer_id"] for r in customer_rows]

    rows = []
    for i in range(n):
        dsar_id = f"DSAR-{tenant_id}-{_uid()}"
        cust_id = random.choice(customer_ids)

        request_type = _pick(fd.get("request_type", "access"))
        sla_breached = _pick_bool(fd.get("sla_breached", False))
        fulfillment_status = _pick(fd.get("fulfillment_status", "pending"))

        submitted_at = _random_timestamp(_random_past_date())
        acknowledged_at = _random_timestamp(_random_past_date())

        # SLA due date = submitted + 30 days
        try:
            sub_date = date.fromisoformat(submitted_at.split("T")[0])
        except Exception:
            sub_date = date.today()
        sla_due_date = (sub_date + timedelta(days=30)).isoformat()

        rejection_reason = ""
        if fulfillment_status == "rejected":
            rejection_reason = "Rejected per policy"

        # Required by the pipeline (field_config.json: "fulfilled_at" ->
        # "fulfilled_date") to compute whether fulfilment happened before or
        # after the SLA deadline. Empty unless the request was fulfilled;
        # timing kept consistent with the independently-chosen sla_breached flag.
        fulfilled_at = ""
        if fulfillment_status == "fulfilled":
            sla_due = date.fromisoformat(sla_due_date)
            if sla_breached:
                fulfilled_date_val = sla_due + timedelta(days=random.randint(1, 20))
            else:
                fulfilled_date_val = sub_date + timedelta(days=random.randint(1, 29))
            fulfilled_at = f"{fulfilled_date_val.isoformat()}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00"

        rows.append({
            "dsar_id": dsar_id,
            "customer_id": cust_id,
            "tenant_id": tenant_id,
            "request_type": request_type,
            "submitted_at": submitted_at,
            "acknowledged_at": acknowledged_at,
            "sla_due_date": sla_due_date,
            "sla_breached": sla_breached,
            "fulfillment_status": fulfillment_status,
            "fulfilled_at": fulfilled_at,
            "rejection_reason": rejection_reason,
            "additional_attributes": "{}",
        })
    return rows


def generate_system_inventory(profile: dict) -> List[dict]:
    """Generate system_inventory rows (no FK dependencies)."""
    n = profile["record_counts"]["n_system_inventory"]
    fd = profile["field_distributions"].get("system_inventory", {})
    tenant_id = profile["tenant_id"]

    rows = []
    for i in range(n):
        sys_id = f"SYS-{tenant_id}-{_uid()}"
        system_name = SYSTEM_NAMES[i % len(SYSTEM_NAMES)]
        system_type = SYSTEM_TYPES[i % len(SYSTEM_TYPES)]

        encryption_type = _pick(fd.get("encryption_type", "AES-256"))
        pii_stored = _pick_bool(fd.get("pii_stored", True))
        encryption_enabled = _pick_bool(fd.get("encryption_enabled", True))
        access_control_enabled = _pick_bool(fd.get("access_control_enabled", True))
        retention_policy_applied = _pick_bool(fd.get("retention_policy_applied", True))
        data_processor_type = _pick(fd.get("data_processor_type", "internal"))
        # Some profiles use "external" as shorthand for a non-internal
        # processor; the DB enum only knows internal/third_party_processor/
        # sub_processor.
        if data_processor_type == "external":
            data_processor_type = "third_party_processor"
        dpa_signed = _pick_bool(fd.get("dpa_signed", True))

        # DB constraint chk_internal_no_dpa_expiry: internal systems can
        # never carry a DPA expiry date, regardless of dpa_signed -- there's
        # no third-party agreement to expire.
        dpa_expiry_date = _random_future_date() if (dpa_signed and data_processor_type != "internal") else ""

        data_types = random.choice(DATA_TYPES_STORED)
        third_party = random.choice(["yes", "no"])

        rows.append({
            "system_id": sys_id,
            "tenant_id": tenant_id,
            "system_name": system_name,
            "system_type": system_type,
            "data_types_stored": data_types,
            "pii_stored": pii_stored,
            "encryption_enabled": encryption_enabled,
            "access_control_enabled": access_control_enabled,
            "retention_policy_applied": retention_policy_applied,
            "third_party_integrations": third_party,
            "data_processor_type": data_processor_type,
            "dpa_signed": dpa_signed,
            "dpa_expiry_date": dpa_expiry_date,
            "additional_attributes": "{}",
        })
    return rows


def generate_policies(profile: dict) -> List[dict]:
    """Generate policies rows (no FK dependencies)."""
    n = profile["record_counts"]["n_policies"]
    fd = profile["field_distributions"].get("policies", {})
    tenant_id = profile["tenant_id"]

    # Check for explicit policies config (e.g. GEN-009)
    explicit = fd.get("explicit_policies", None)
    if explicit:
        rows = []
        for j, ep in enumerate(explicit):
            pol_id = f"POL-{tenant_id}-{_uid()}"
            eff_date = _random_past_date()
            rows.append({
                "policy_id": pol_id,
                "tenant_id": tenant_id,
                "policy_type": ep.get("policy_type", "retention"),
                "policy_name": POLICY_NAMES.get(ep.get("policy_type", "retention"), "Policy"),
                "policy_value_numeric": ep.get("policy_value_numeric", 365),
                "policy_value_unit": ep.get("policy_value_unit", "days"),
                "effective_date": eff_date,
                "last_updated": eff_date,
                "is_active": ep.get("is_active", True),
                "additional_attributes": "{}",
            })
        # Fill remaining slots with default policies
        remaining = n - len(rows)
        for j in range(remaining):
            pol_id = f"POL-{tenant_id}-{_uid()}"
            pol_type = _pick(fd.get("policy_type", "retention"))
            eff_date = _random_past_date()
            rows.append({
                "policy_id": pol_id,
                "tenant_id": tenant_id,
                "policy_type": pol_type,
                "policy_name": POLICY_NAMES.get(pol_type, "Policy"),
                "policy_value_numeric": 365,
                "policy_value_unit": _pick(fd.get("policy_value_unit", "days")),
                "effective_date": eff_date,
                "last_updated": eff_date,
                "is_active": True,
                "additional_attributes": "{}",
            })
        return rows

    # Standard distribution-based generation
    rows = []
    for j in range(n):
        pol_id = f"POL-{tenant_id}-{_uid()}"
        pol_type = _pick(fd.get("policy_type", "retention"))
        is_active = _pick_bool(fd.get("is_active", True))
        eff_date = _random_past_date()

        rows.append({
            "policy_id": pol_id,
            "tenant_id": tenant_id,
            "policy_type": pol_type,
            "policy_name": POLICY_NAMES.get(pol_type, "Policy"),
            "policy_value_numeric": 365,
            "policy_value_unit": _pick(fd.get("policy_value_unit", "days")),
            "effective_date": eff_date,
            "last_updated": eff_date,
            "is_active": is_active,
            "additional_attributes": "{}",
        })
    return rows


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CSV WRITER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def write_csv(rows: List[dict], file_path: Path):
    """Write a list of dicts as a CSV file."""
    import csv
    if not rows:
        # Write an empty CSV with headers from the first expected key set
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch()
        return

    file_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PROFILE PROCESSOR
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def process_profile(profile: dict) -> dict:
    """
    Process a single profile:
    1. Generate all 10 CSVs in FK order
    2. Copy to pipeline-expected location
    3. Run anonymization + compliance pipeline
    4. Insert result into evaluation_results
    5. Return a report dict
    """
    tenant_id = profile["tenant_id"]
    profile_name = profile["profile_name"]
    report = {
        "tenant_id": tenant_id,
        "profile_name": profile_name,
        "row_counts": {},
        "triggered_rules": [],
        "risk_score": None,
        "risk_tier": None,
        "status": "pending",
        "error": None,
    }

    print(f"\n{'='*60}")
    print(f"  Processing: {tenant_id} â€” {profile_name}")
    print(f"{'='*60}")

    # â”€â”€ Step 1: Generate CSVs in FK order â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # 1a. No FK dependencies
    print(f"  [1/10] Generating governance_config...")
    gov_rows = generate_governance_config(profile)
    print(f"  [2/10] Generating system_inventory...")
    sys_rows = generate_system_inventory(profile)
    print(f"  [3/10] Generating policies...")
    pol_rows = generate_policies(profile)

    # 1b. Customer first (root for FKs)
    print(f"  [4/10] Generating customer_master...")
    cust_rows = generate_customer_master(profile)

    # 1c. Consent depends on customer
    print(f"  [5/10] Generating consent_records...")
    consent_rows = generate_consent_records(profile, cust_rows)

    # 1d. Transaction depends on consent (â†’ customer)
    print(f"  [6/10] Generating transaction_events...")
    txn_rows = generate_transaction_events(profile, consent_rows, sys_rows)

    # 1e. Access, lifecycle, security, dsar depend on customer
    print(f"  [7/10] Generating access_logs...")
    access_rows = generate_access_logs(profile, cust_rows)
    print(f"  [8/10] Generating data_lifecycle...")
    lifecycle_rows = generate_data_lifecycle(profile, cust_rows)
    print(f"  [9/10] Generating security_events...")
    sec_rows = generate_security_events(profile, cust_rows)
    print(f"  [10/10] Generating dsar_requests...")
    dsar_rows = generate_dsar_requests(profile, cust_rows)

    report["row_counts"] = {
        "governance_config": len(gov_rows),
        "customer_master": len(cust_rows),
        "consent_records": len(consent_rows),
        "transaction_events": len(txn_rows),
        "access_logs": len(access_rows),
        "data_lifecycle": len(lifecycle_rows),
        "security_events": len(sec_rows),
        "dsar_requests": len(dsar_rows),
        "system_inventory": len(sys_rows),
        "policies": len(pol_rows),
    }

    # â”€â”€ Step 2: Write CSVs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Save to data/raw_synthetic/{tenant_id}/
    synthetic_dir = RAW_SYNTHETIC_DIR / tenant_id
    synthetic_dir.mkdir(parents=True, exist_ok=True)

    csv_map = {
        "governance_config.csv": gov_rows,
        "customer_master.csv": cust_rows,
        "consent_records.csv": consent_rows,
        "transaction_events.csv": txn_rows,
        "access_logs.csv": access_rows,
        "data_lifecycle.csv": lifecycle_rows,
        "security_events.csv": sec_rows,
        "dsar_requests.csv": dsar_rows,
        "system_inventory.csv": sys_rows,
        "policies.csv": pol_rows,
    }

    for filename, rows in csv_map.items():
        write_csv(rows, synthetic_dir / filename)

    print(f"  [OK] CSVs written to {synthetic_dir}")

    # â”€â”€ Step 3: Copy to pipeline-expected location â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Pipeline reads from: data/tenants/{tenant_id}/raw/
    pipeline_dir = tenant_raw_dir(tenant_id)
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    for filename in csv_map:
        src = synthetic_dir / filename
        dst = pipeline_dir / filename
        shutil.copy2(src, dst)

    print(f"  [OK] CSVs copied to {pipeline_dir}")

    # â”€â”€ Step 4: Run anonymization pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"  Running anonymization pipeline...")
    anon_result = run_anonymization_pipeline(tenant_id)
    if anon_result.get("status") != "success":
        msg = anon_result.get("message", "Unknown anonymization error")
        print(f"  [FAIL] Anonymization FAILED: {msg}")
        report["status"] = "anon_failed"
        report["error"] = msg
        return report
    print(f"  [OK] Anonymization complete: {anon_result.get('rows_written', {})}")

    # â”€â”€ Step 5: Run compliance analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"  Running compliance analysis...")
    result = run_compliance_analysis(tenant_id)
    risk_score = result.get("risk_score", 0)
    risk_tier = result.get("risk_tier", "UNKNOWN")
    report["risk_score"] = risk_score
    report["risk_tier"] = risk_tier
    report["status"] = "success"

    # Collect triggered rules for report
    contributions = result.get("risk_contributions", {})
    for rule_id, contrib_val in contributions.items():
        report["triggered_rules"].append(f"{rule_id} (contribution={contrib_val})")

    print(f"  [OK] Risk Score: {risk_score} | Tier: {risk_tier}")
    print(f"  [OK] Rules triggered: {list(contributions.keys())}")

    # â”€â”€ Step 6: Write to evaluation_results â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"  Writing to evaluation_results...")
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_results
                    (tenant_id, result_json, risk_score, created_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (
                    tenant_id,
                    json.dumps(result, default=str),
                    risk_score,
                ),
            )
        conn.commit()
        conn.close()
        print(f"  [OK] evaluation_results written")
    except Exception as e:
        print(f"  [FAIL] DB write failed: {e}")
        report["error"] = f"DB write failed: {e}"
        # Don't mark as failed â€” the pipeline ran successfully
        report["status"] = "success_no_db"

    return report


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# REPORT WRITER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def write_report(reports: List[dict]):
    """Write generation_report.txt to repo root."""
    lines = []
    lines.append("=" * 70)
    lines.append("  SYNTHETIC DATA GENERATION REPORT")
    lines.append(f"  Generated: {datetime.now().isoformat()}")
    lines.append("=" * 70)
    lines.append("")

    success_count = sum(1 for r in reports if r["status"].startswith("success"))
    fail_count = len(reports) - success_count

    lines.append(f"  Total profiles: {len(reports)}")
    lines.append(f"  Successful:     {success_count}")
    lines.append(f"  Failed:         {fail_count}")
    lines.append("")

    for r in reports:
        lines.append("-" * 70)
        lines.append(f"  Tenant:       {r['tenant_id']}")
        lines.append(f"  Profile:      {r['profile_name']}")
        lines.append(f"  Status:       {r['status']}")

        if r.get("error"):
            lines.append(f"  Error:        {r['error']}")

        lines.append(f"  Row Counts:")
        for table, count in r.get("row_counts", {}).items():
            lines.append(f"    {table:30s} â†’ {count}")

        if r.get("risk_score") is not None:
            lines.append(f"  Risk Score:   {r['risk_score']}")
            lines.append(f"  Risk Tier:    {r['risk_tier']}")

        if r.get("triggered_rules"):
            lines.append(f"  Triggered Rules:")
            for rule in r["triggered_rules"]:
                lines.append(f"    - {rule}")

        lines.append("")

    lines.append("=" * 70)
    lines.append("  END OF REPORT")
    lines.append("=" * 70)

    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\n[OK] Report written to {REPORT_PATH}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# MAIN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def main():
    print("=" * 70)
    print("  Fin-Comply â€” Synthetic Data Generator")
    print("  Part 1 of XGBoost ML Training Pipeline")
    print("=" * 70)

    # Load config
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config file not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    print(f"\nLoaded {len(profiles)} profiles from {CONFIG_PATH}")
    print(f"Output: {RAW_SYNTHETIC_DIR}")
    print(f"Report: {REPORT_PATH}")

    # Set random seed for reproducibility
    random.seed(42)

    # Process each profile
    reports = []
    for idx, profile in enumerate(profiles, 1):
        tenant_id = profile["tenant_id"]
        profile_name = profile["profile_name"]
        print(f"\n[{idx}/{len(profiles)}] {tenant_id}: {profile_name}")

        try:
            report = process_profile(profile)
            reports.append(report)
        except Exception as e:
            print(f"  [FAIL] FATAL ERROR for {tenant_id}: {e}")
            traceback.print_exc()
            reports.append({
                "tenant_id": tenant_id,
                "profile_name": profile_name,
                "row_counts": {},
                "triggered_rules": [],
                "risk_score": None,
                "risk_tier": None,
                "status": "fatal_error",
                "error": str(e),
            })

    # Write report
    write_report(reports)

    # Summary
    print("\n" + "=" * 70)
    print("  GENERATION COMPLETE")
    success = sum(1 for r in reports if r["status"].startswith("success"))
    print(f"  {success}/{len(reports)} profiles processed successfully")
    print("=" * 70)


if __name__ == "__main__":
    raise SystemExit(
        "\n"
        "========================================================\n"
        "  DEPRECATED: generate_data.py must not be executed.   \n"
        "========================================================\n"
        "  Reason: This generator produces un-hashed field names \n"
        "  (consent_id, customer_id) and phantom FK values that  \n"
        "  corrupted the compliance engine and ML training data.  \n"
        "                                                         \n"
        "  Use the canonical generator instead:                   \n"
        "    python -m data.generate_test_tenants                 \n"
        "    python data/generate_test_tenants.py                 \n"
        "========================================================\n"
    )

