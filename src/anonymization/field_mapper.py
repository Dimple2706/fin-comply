import pandas as pd
from datetime import date
from typing import Dict, List, Union, Any
import os
from .hasher import hash_id, validate_hash_string

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPER FUNCTIONS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def _truncate_to_date(value: Any) -> Union[str, None]:
    """
    Technique 2 â€” Timestamp Truncation
    Evidence: ISO/IEC 20889:2018 Section 8.3
    Truncates full timestamps to date only to mitigate precise re-identification.
    """
    if pd.isna(value):
        return None
    try:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip().split(" ")[0].split("T")[0]).isoformat()
            except ValueError:
                pass
        
        # Prefer pandas' flexible parser so both ISO and DD-MM-YYYY values work.
        dt = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if not pd.isna(dt):
            return dt.date().isoformat()

        # Fallback for already-normalized timestamp strings.
        vs = str(value).strip().split(" ")[0].split("T")[0]
        if len(vs) == 10 and len(vs.split("-")) == 3:
            parts = vs.split("-")
            if len(parts[0]) == 4:
                return vs
            # Handle DD-MM-YYYY manually if pandas couldn't infer it.
            if len(parts[2]) == 4:
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        return None
    except:
        return None

def _parse_date(value: Any) -> Union[date, None]:
    """
    Parse CSV-provided date values using the same tolerance as truncation.
    Accepts ISO dates, DD-MM-YYYY, and timestamp strings with time parts.
    """
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.split("T")[0])
        except ValueError:
            pass
            
    date_text = _truncate_to_date(value)
    if not date_text:
        return None
    try:
        return date.fromisoformat(date_text)
    except ValueError:
        return None

def _bucket_user_count(value: Any) -> Union[str, None]:
    """
    Technique 3 â€” Bucketing
    Evidence: ISO/IEC 20889:2018 Section 8.3
    Maps exact integer counts to user_count_band ENUM.
    """
    if pd.isna(value):
        return None
    try:
        count = int(float(value)) # handles string floats like "10.0"
        if count <= 0:
            return None
        if count <= 100:
            return "minimal"
        elif count <= 1000:
            return "moderate"
        elif count <= 10000:
            return "large"
        else:
            return "critical"
    except (ValueError, TypeError):
        return None

class EnumValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Enum Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

class GovernanceValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Governance Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

class ConsentValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Consent Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

class SecurityEventValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Security Event Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

class TransactionValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Transaction Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

class LifecycleValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"Lifecycle Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

def _mask_email(email: str) -> Union[str, None]:
    if not email:
        return None
    email_str = str(email).strip()
    if "@" not in email_str:
        return email_str
    parts = email_str.split("@")
    local = parts[0]
    domain = parts[1]
    if len(local) > 0:
        first = local[0]
        return f"{first}***@{domain}"
    return email_str

def _validate_enum(value: Any, valid_values: list, field_name: str, filename: str, row_number: int, required: bool = True) -> Union[str, None]:
    """
    Validates ENUM values.
    Returns None if missing and optional (preserving missing evidence).
    Raises EnumValidationError if required and missing, or if invalid.
    """
    if pd.isna(value) or str(value).strip() == "" or str(value).strip() == "None":
        if required:
            raise EnumValidationError(
                filename=filename,
                row_number=row_number,
                field=field_name,
                error_code="MISSING_ENUM_VALUE",
                explanation=f"Required enum field '{field_name}' is missing or blank."
            )
        return None
        
    val_str = str(value).strip()
    if val_str in valid_values:
        return val_str
        
    raise EnumValidationError(
        filename=filename,
        row_number=row_number,
        field=field_name,
        error_code="INVALID_ENUM_VALUE",
        explanation=f"Value '{val_str}' is invalid for enum {field_name}. Valid values: {valid_values}"
    )

def _safe_bool(value: Any) -> bool:
    """
    Safely converts varying boolean representations (NaN, TRUE, 1, "Yes") to Python bool.
    """
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    return val_str in ["true", "1", "yes", "y", "t"]

def _extract_hash(row: pd.Series, hash_col: str, id_col: str, tenant_id: str) -> Union[str, None]:
    """
    Extracts a hash value:
    1. If hash_col is already present and non-null (canonical format), returns it after strict format validation.
    2. Else if id_col is present and non-null (raw format), applies hash_id(id_col, tenant_id).
    3. Else returns None.
    """
    val = row.get(hash_col)
    if pd.notna(val) and str(val).strip() and str(val).strip() != "None":
        h_val = str(val).strip()
        if not validate_hash_string(h_val):
            raise ValueError(f"Invalid pre-hashed format: '{h_val}'")
        return h_val
    id_val = row.get(id_col)
    if pd.notna(id_val) and str(id_val).strip() and str(id_val).strip() != "None":
        version = os.getenv("HASH_VERSION", "v2")
        return hash_id(str(id_val).strip(), tenant_id, version=version)
    return None

def _first_present(row: pd.Series, *keys: str) -> Any:
    """
    Return the first non-null value among possible source columns.
    Useful where upload CSV headers differ from DB target field names.
    """
    for key in keys:
        value = row.get(key)
        if pd.notna(value):
            return value
    return None

# ═══════════════════════════════════════════════════════════════
# PER-TABLE ANONYMIZERS
# ═══════════════════════════════════════════════════════════════

def _anonymize_governance_config(df: pd.DataFrame, tenant_id: str) -> dict:
    row = df.iloc[0]
    dpo_assigned = _safe_bool(row.get("dpo_assigned"))

    sdf_value = row.get("is_significant_data_fiduciary")
    if pd.isna(sdf_value) or str(sdf_value).strip() == "":
        is_significant_data_fiduciary = None
    else:
        normalized_sdf = str(sdf_value).strip().lower()
        if normalized_sdf not in {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f"}:
            raise GovernanceValidationError(
                "governance_config.csv", 2, "is_significant_data_fiduciary",
                "INVALID_BOOLEAN_VALUE",
                "SDF applicability must be an explicit true/false value when supplied."
            )
        is_significant_data_fiduciary = normalized_sdf in {"true", "1", "yes", "y", "t"}
    
    dpo_contact = _first_present(row, "dpo_contact_masked", "dpo_contact")
    if dpo_assigned:
        if not dpo_contact or str(dpo_contact).strip() == "" or str(dpo_contact).strip() == "None":
            raise GovernanceValidationError("governance_config.csv", 2, "dpo_contact_masked", "MISSING_DPO_CONTACT", "DPO contact is required when DPO is assigned.")
        dpo_contact_masked = _mask_email(dpo_contact)
    else:
        dpo_contact_masked = _mask_email(dpo_contact) if dpo_contact else None

    tenant_name_val = row.get("tenant_name")
    if pd.isna(tenant_name_val) or str(tenant_name_val).strip() in ("", "None"):
        raise GovernanceValidationError("governance_config.csv", 2, "tenant_name", "MISSING_TENANT_NAME", "Tenant name is required.")
    tenant_name = str(tenant_name_val).strip()

    return {
        "tenant_id": tenant_id, # Gate 1
        "tenant_name": tenant_name, # Gate 1
        "is_significant_data_fiduciary": is_significant_data_fiduciary,
        "grievance_endpoint_available": _safe_bool(row.get("grievance_endpoint_available")), # Gate 2
        "dpo_assigned": dpo_assigned, # Gate 2
        "dpo_contact_masked": dpo_contact_masked,
        "audit_frequency_days": int(row["audit_frequency_days"]) if pd.notna(row.get("audit_frequency_days")) else 90, # Gate 3
        "last_audit_date": _truncate_to_date(row.get("last_audit_date")), # Gate 2, Technique 2
        "risk_level": _validate_enum(row.get("risk_level"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "risk_level", "governance_config.csv", 2, required=("risk_level" in row)) # Gate 2, Technique 5
    }

def _anonymize_customer_master(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        is_minor = _safe_bool(row.get("is_minor"))
        data_principal_type = _validate_enum(row.get("data_principal_type"), ["individual", "minor", "NRI", "OCI", "PIO"], "data_principal_type", "customer_master.csv", row_num, required=("data_principal_type" in row))
        if is_minor:
            data_principal_type = "minor"
        records.append({
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "is_minor": is_minor, # Gate 2
            "data_principal_type": data_principal_type, # Gate 3, Technique 5
            "account_status": _validate_enum(row.get("account_status"), ["active", "dormant", "closed"], "account_status", "customer_master.csv", row_num, required=("account_status" in row)), # Gate 2, Technique 5
            "kyc_status": _validate_enum(row.get("kyc_status"), ["verified", "pending", "expired", "rejected"], "kyc_status", "customer_master.csv", row_num, required=("kyc_status" in row)), # Gate 2, Technique 5
            "country": "IN" if ("country" not in row) else (str(row["country"]).strip() if (pd.notna(row.get("country")) and str(row["country"]).strip() not in ("", "None")) else None), # Gate 2
            "created_at": _truncate_to_date(row.get("created_at")) # Gate 2, Technique 2
        })
    return records

def _anonymize_consent_records(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        consent_status = _validate_enum(row.get("consent_status"), ["active", "expired", "revoked", "withdrawn", "granted"], "consent_status", "consent_records.csv", row_num, required=("consent_status" in row))
        consent_date = _truncate_to_date(_first_present(row, "consent_date", "consent_timestamp"))
        withdrawal_date = _truncate_to_date(_first_present(row, "withdrawal_date", "withdrawal_timestamp"))
        notice_provided = _safe_bool(row.get("notice_provided"))
        is_bundled = _safe_bool(row.get("is_bundled"))

        consent_channel = _validate_enum(
            row.get("consent_channel"),
            ["app", "web", "branch", "implicit", "pre_ticked"],
            "consent_channel",
            "consent_records.csv",
            row_num,
            required=("consent_channel" in row)
        )

        if not notice_provided or is_bundled:
            consent_channel = "implicit" if consent_channel not in {"implicit", "pre_ticked"} else consent_channel

        if consent_status == "withdrawn" and not withdrawal_date:
            raise ConsentValidationError("consent_records.csv", row_num, "withdrawal_date", "MISSING_WITHDRAWAL_DATE", "Withdrawal date must be specified when status is withdrawn.")

        sharing_permitted_val = row.get("third_party_sharing_permitted")
        if pd.isna(sharing_permitted_val) or sharing_permitted_val is None or str(sharing_permitted_val).strip().lower() in ("", "none", "nan"):
            third_party_sharing_permitted = None
        else:
            third_party_sharing_permitted = _safe_bool(sharing_permitted_val)

        records.append({
            "consent_hash": _extract_hash(row, "consent_hash", "consent_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "consent_status": consent_status, # Gate 2, Technique 5
            "consent_date": consent_date, # Gate 2, Technique 2
            "expiry_date": _truncate_to_date(_first_present(row, "expiry_date", "expiry_timestamp")), # Gate 2, Technique 2
            "withdrawal_date": withdrawal_date, # Gate 2, Technique 2
            "consented_purpose": _validate_enum(row.get("consented_purpose"), ["loan_processing", "emi_collection", "kyc_verification", "credit_check", "marketing", "account_management", "fraud_detection", "data_enrichment"], "consented_purpose", "consent_records.csv", row_num, required=("consented_purpose" in row)), # Gate 2, Technique 5
            "consent_version": "v1.0" if ("consent_version" not in row) else (str(row["consent_version"]).strip() if (pd.notna(row.get("consent_version")) and str(row["consent_version"]).strip() not in ("", "None")) else None), # Gate 3
            "notice_provided": notice_provided, # Gate 2
            "is_bundled": is_bundled, # Gate 2
            "consent_channel": consent_channel, # Gate 3, Technique 5
            "guardian_consent_hash": _extract_hash(row, "guardian_consent_hash", "guardian_consent_id", tenant_id), # Gate 2, Technique 1
            "third_party_sharing_permitted": third_party_sharing_permitted
        })
    return records

def _anonymize_transaction_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    results = []
    for index, row in df.iterrows():
        row_num = index + 2
        tp_hash = _extract_hash(row, "third_party_hash", "third_party_id", tenant_id)

        is_cross_border = _safe_bool(row.get("is_cross_border"))
        transfer_country = row.get("transfer_country")
        if pd.isna(transfer_country) or str(transfer_country).strip() in ("", "None", "nan"):
            transfer_country = None
        else:
            transfer_country = str(transfer_country).strip()

        if is_cross_border:
            if not transfer_country:
                raise TransactionValidationError("transaction_events.csv", row_num, "transfer_country", "MISSING_TRANSFER_COUNTRY", "Transfer country is required for cross-border transactions.")

        restriction_value = row.get("transfer_restriction_compliant")
        if pd.isna(restriction_value) or restriction_value is None or str(restriction_value).strip().lower() in ("", "none", "nan"):
            transfer_restriction_compliant = None
        else:
            transfer_restriction_compliant = _safe_bool(restriction_value)

        reference_value = row.get("transfer_assessment_reference")
        if pd.isna(reference_value) or reference_value is None or str(reference_value).strip().lower() in ("", "none", "nan"):
            transfer_assessment_reference = None
        else:
            transfer_assessment_reference = str(reference_value).strip()

        results.append({
            "event_hash": _extract_hash(row, "event_hash", "event_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "consent_hash": _extract_hash(row, "consent_hash", "consent_id", tenant_id), # Gate 1, Technique 1
            "event_type": _validate_enum(row.get("event_type"), ["credit_check", "loan_disbursal", "emi_collection", "kyc_verification", "marketing_push", "data_enrichment", "account_update", "fraud_check"], "event_type", "transaction_events.csv", row_num, required=("event_type" in row)), # Gate 2, Technique 5
            "processing_purpose": _validate_enum(row.get("processing_purpose"), ["loan_processing", "emi_collection", "kyc_verification", "credit_check", "marketing", "account_management", "fraud_detection", "data_enrichment", "data_brokering"], "processing_purpose", "transaction_events.csv", row_num, required=("processing_purpose" in row)), # Gate 2, Technique 5
            "event_date": _truncate_to_date(_first_present(row, "event_date", "timestamp")), # Gate 2, Technique 2
            "shared_with_third_party": _safe_bool(row.get("shared_with_third_party")), # Gate 2
            "third_party_hash": tp_hash, # Gate 2, Technique 1
            "is_cross_border": is_cross_border, # Gate 2
            "transfer_country": transfer_country,
            "transfer_restriction_compliant": transfer_restriction_compliant,
            "transfer_assessment_reference": transfer_assessment_reference
        })
    return results

def _anonymize_access_logs(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        
        pii_fields_justified_val = row.get("pii_fields_justified")
        if pd.isna(pii_fields_justified_val) or pii_fields_justified_val is None or str(pii_fields_justified_val).strip().lower() in ("", "none", "nan"):
            pii_fields_justified = None
        else:
            pii_fields_justified = _safe_bool(pii_fields_justified_val)

        access_authorized_val = row.get("access_authorized")
        if pd.isna(access_authorized_val) or access_authorized_val is None or str(access_authorized_val).strip().lower() in ("", "none", "nan"):
            access_authorized = None
        else:
            normalized_authorized = str(access_authorized_val).strip().lower()
            if normalized_authorized not in {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f"}:
                raise EnumValidationError(
                    "access_logs.csv", row_num, "access_authorized",
                    "INVALID_BOOLEAN_VALUE",
                    "access_authorized must be an explicit true/false value when supplied."
                )
            access_authorized = normalized_authorized in {"true", "1", "yes", "y", "t"}

        records.append({
            "access_hash": _extract_hash(row, "access_hash", "access_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "employee_hash": _extract_hash(row, "employee_hash", "employee_id", tenant_id), # Gate 1, Technique 1
            "employee_role": _validate_enum(row.get("employee_role"), ["collections_agent", "underwriter", "customer_support", "data_analyst", "compliance_officer", "engineer", "manager"], "employee_role", "access_logs.csv", row_num, required=("employee_role" in row)), # Gate 2, Technique 5
            "accessed_pii": _safe_bool(row.get("accessed_pii")), # Gate 2
            "pii_fields_accessed": (
                str(row["pii_fields_accessed"])
                if pd.notna(row.get("pii_fields_accessed")) and _safe_bool(row.get("accessed_pii"))
                else None
            ), # Gate 2
            "access_reason": _validate_enum(row.get("access_reason"), ["loan_review", "kyc_check", "fraud_investigation", "support_query", "data_export"], "access_reason", "access_logs.csv", row_num, required=("access_reason" in row)), # Gate 2, Technique 5
            "access_outcome": _validate_enum(row.get("access_outcome"), ["granted", "denied"], "access_outcome", "access_logs.csv", row_num, required=("access_outcome" in row)), # Gate 2, Technique 5
            "data_volume_accessed": _validate_enum(row.get("data_volume_accessed"), ["low", "medium", "high", "bulk"], "data_volume_accessed", "access_logs.csv", row_num, required=("data_volume_accessed" in row)), # Gate 2, Technique 5
            "access_date": _truncate_to_date(_first_present(row, "access_date", "timestamp")), # Gate 2, Technique 2
            "system_hash": _extract_hash(row, "system_hash", "system_id", tenant_id),
            "pii_fields_justified": pii_fields_justified,
            "access_authorized": access_authorized,
            "additional_attributes": (
                str(row["additional_attributes"])
                if pd.notna(row.get("additional_attributes"))
                else None
            )
        })
    return records

def _anonymize_data_lifecycle(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        retention_status = _validate_enum(row.get("retention_status"), ["active", "expired", "pending_deletion", "deleted"], "retention_status", "data_lifecycle.csv", row_num, required=("retention_status" in row))
        retention_expiry_date = _truncate_to_date(row.get("retention_expiry_date"))
        erasure_requested = _safe_bool(row.get("erasure_requested"))
        purpose_completed = _safe_bool(row.get("purpose_completed"))
        erasure_date = _truncate_to_date(_first_present(row, "erasure_date", "erasure_timestamp")) if erasure_requested else None

        erasure_request_source = _validate_enum(row.get("erasure_request_source"), ["user", "system"], "erasure_request_source", "data_lifecycle.csv", row_num, required=False) if erasure_requested else None
        if erasure_requested:
            if not erasure_request_source or str(erasure_request_source).strip() in ("", "None", "nan"):
                raise LifecycleValidationError("data_lifecycle.csv", row_num, "erasure_request_source", "MISSING_ERASURE_SOURCE", "Erasure request source is required when erasure is requested.")

        records.append({
            "lifecycle_hash": _extract_hash(row, "lifecycle_hash", "lifecycle_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "data_category": _validate_enum(row.get("data_category"), ["kyc_documents", "transaction_history", "credit_score", "contact_info", "device_info"], "data_category", "data_lifecycle.csv", row_num, required=("data_category" in row)), # Gate 2, Technique 5
            "retention_expiry_date": retention_expiry_date, # Gate 2, Technique 2
            "retention_status": retention_status, # Gate 2, Technique 5
            "purpose_completed": purpose_completed, # Gate 2
            "erasure_requested": erasure_requested, # Gate 2
            "erasure_date": erasure_date, # Gate 2, Technique 2
            "legal_hold_flag": _safe_bool(row.get("legal_hold_flag")), # Gate 2
            "erasure_request_source": erasure_request_source # Gate 2, Technique 5
        })
    return records

def _anonymize_security_events(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        breach_detected = _safe_bool(row.get("breach_detected"))
        
        raw_date = _first_present(row, "breach_confirmed_date", "breach_confirmed_at")
        if pd.notna(raw_date) and str(raw_date).strip() not in ("", "None"):
            breach_confirmed_date = _truncate_to_date(raw_date)
            if not breach_confirmed_date:
                raise SecurityEventValidationError("security_events.csv", row_num, "breach_confirmed_date", "INVALID_DATE_FORMAT", "Malformed breach confirmed date supplied.")
        else:
            breach_confirmed_date = None

        raw_delay = row.get("notification_delay_hours")
        if pd.notna(raw_delay) and str(raw_delay).strip() not in ("", "None"):
            try:
                notification_delay_hours = int(float(raw_delay))
            except (ValueError, TypeError):
                raise SecurityEventValidationError("security_events.csv", row_num, "notification_delay_hours", "INVALID_DELAY_FORMAT", "Notification delay hours must be a valid integer.")
            if notification_delay_hours < 0:
                raise SecurityEventValidationError("security_events.csv", row_num, "notification_delay_hours", "INVALID_DELAY_VALUE", "Notification delay hours must be non-negative.")
        else:
            notification_delay_hours = None
            
        raw_val = row.get("affected_user_count")
        bucketed = _bucket_user_count(raw_val)
        if bucketed:
            affected_user_count = bucketed
        elif pd.notna(raw_val) and str(raw_val).strip() and str(raw_val).strip() != "None" and str(raw_val).strip() != "0":
            affected_user_count = _validate_enum(raw_val, ["minimal", "moderate", "large", "critical"], "affected_user_count", "security_events.csv", row_num, required=False)
        else:
            affected_user_count = None
            
        dc_val = row.get("data_categories_breached")
        if pd.isna(dc_val) or str(dc_val).strip() in ("", "None"):
            data_categories_breached = None
        else:
            data_categories_breached = str(dc_val).strip()

        records.append({
            "security_hash": _extract_hash(row, "security_hash", "security_id", tenant_id), # Gate 1, Technique 1
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "pii_encrypted": _safe_bool(row.get("pii_encrypted")), # Gate 2
            "encryption_type": _validate_enum(row.get("encryption_type"), ["AES-256", "AES-128", "RSA-2048", "none", "md5"], "encryption_type", "security_events.csv", row_num, required=("encryption_type" in row)), # Gate 2, Technique 5
            "breach_detected": breach_detected, # Gate 2
            "breach_confirmed_date": breach_confirmed_date, # Gate 2, Technique 2
            "notification_delay_hours": notification_delay_hours, # Gate 2
            "affected_user_count": affected_user_count, # Gate 2, Technique 3
            "data_categories_breached": data_categories_breached, # Gate 2
            "security_audit_flag": _safe_bool(row.get("security_audit_flag")) # Gate 2
        })
    return records

class SystemInventoryValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"System Inventory Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

def _anonymize_dsar_requests(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    results = []
    for index, row in df.iterrows():
        row_num = index + 2
        
        submitted_date = _truncate_to_date(_first_present(row, "submitted_date", "submitted_at"))
        sla_due_date = _truncate_to_date(row.get("sla_due_date"))
        fulfilled_date = _truncate_to_date(_first_present(row, "fulfilled_date", "fulfilled_at"))
        fulfillment_status = _validate_enum(row.get("fulfillment_status"), ["pending", "fulfilled", "partially_fulfilled", "rejected"], "fulfillment_status", "dsar_requests.csv", row_num, required=("fulfillment_status" in row))
        sla_breached = _safe_bool(row.get("sla_breached"))
        
        if not submitted_date:
            raise DsarValidationError("dsar_requests.csv", row_num, "submitted_date", "MISSING_DATE", "submitted_date is mandatory and cannot be fabricated.")
            
        submitted_dt = _parse_date(submitted_date)
        if not submitted_dt:
            raise DsarValidationError("dsar_requests.csv", row_num, "submitted_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
            
        if not sla_due_date:
            raise DsarValidationError("dsar_requests.csv", row_num, "sla_due_date", "MISSING_DATE", "sla_due_date is mandatory and cannot be fabricated.")
            
        sla_due_dt = _parse_date(sla_due_date)
        if not sla_due_dt:
            raise DsarValidationError("dsar_requests.csv", row_num, "sla_due_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
            
        # The DPDP Act/Rules do not prescribe a universal 30-day deadline for
        # access, correction, erasure, or nomination requests. Preserve the
        # tenant's evidenced SLA, but reject a logically impossible deadline.
        if sla_due_dt <= submitted_dt:
            raise DsarValidationError(
                "dsar_requests.csv", row_num, "sla_due_date",
                "INVALID_SLA_SEQUENCE",
                "sla_due_date must be later than submitted_date; no statutory 30-day deadline is fabricated."
            )
 
        if fulfillment_status == "fulfilled":
            if not fulfilled_date:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "MISSING_EVIDENCE", "fulfilled_date is mandatory when fulfillment_status is fulfilled.")
            
            fulfilled_dt = _parse_date(fulfilled_date)
            if not fulfilled_dt:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "INVALID_DATE_FORMAT", "Must be a valid ISO YYYY-MM-DD date.")
                
            if fulfilled_dt < submitted_dt:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "LOGICAL_CONTRADICTION", "fulfilled_date must not be before submitted_date.")
                
            is_actually_breached = fulfilled_dt > sla_due_dt
            if sla_breached != is_actually_breached:
                raise DsarValidationError("dsar_requests.csv", row_num, "sla_breached", "CONTRADICTION", f"sla_breached flag ({sla_breached}) contradicts evidence (fulfilled: {fulfilled_dt}, due: {sla_due_dt}).")
                
            rejection_reason = None
        elif fulfillment_status == "pending":
            if fulfilled_date:
                raise DsarValidationError("dsar_requests.csv", row_num, "fulfilled_date", "INVALID_EVIDENCE", "fulfilled_date must be empty when fulfillment_status is pending.")
            rejection_reason = None
        elif fulfillment_status == "rejected":
            fulfilled_date = None
            rejection_reason = str(row["rejection_reason"]) if pd.notna(row.get("rejection_reason")) else None
            if not rejection_reason:
                raise DsarValidationError("dsar_requests.csv", row_num, "rejection_reason", "MISSING_REASON", "rejection_reason is mandatory when fulfillment_status is rejected.")
        else:
            fulfilled_date = None
            rejection_reason = None
 
        results.append({
            "dsar_hash": _extract_hash(row, "dsar_hash", "dsar_id", tenant_id),
            "customer_hash": _extract_hash(row, "customer_hash", "customer_id", tenant_id),
            "tenant_id": tenant_id,
            "request_type": _validate_enum(row.get("request_type"), ["access", "correction", "erasure", "nomination"], "request_type", "dsar_requests.csv", row_num, required=("request_type" in row)),
            "submitted_date": submitted_date,
            "acknowledged_date": _truncate_to_date(_first_present(row, "acknowledged_date", "acknowledged_at")),
            "sla_due_date": sla_due_date,
            "sla_breached": sla_breached,
            "fulfilled_date": fulfilled_date,
            "fulfillment_status": fulfillment_status,
            "rejection_reason": rejection_reason,
        })
    return results
 
def _anonymize_system_inventory(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        data_processor_type = _validate_enum(
            row.get("data_processor_type"),
            ["internal", "third_party_processor", "sub_processor"],
            "data_processor_type",
            "system_inventory.csv",
            row_num,
            required=("data_processor_type" in row)
        )
 
        dpa_signed = _safe_bool(row.get("dpa_signed"))
        dpa_expiry_date = _truncate_to_date(row.get("dpa_expiry_date")) or None
        
        if "system_name" not in row:
            system_name = None
        else:
            sys_name = row.get("system_name")
            if pd.isna(sys_name) or str(sys_name).strip() in ("", "None"):
                system_name = None
            else:
                system_name = str(sys_name).strip()

        records.append({
            "system_hash": _extract_hash(row, "system_hash", "system_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "system_name": system_name, # Gate 1
            "system_type": _validate_enum(row.get("system_type"), ["crm", "core_banking", "analytics", "kyc_platform", "payment_gateway", "data_warehouse"], "system_type", "system_inventory.csv", row_num, required=("system_type" in row)), # Gate 2, Technique 5
            "pii_stored": _safe_bool(row.get("pii_stored")), # Gate 2
            "encryption_enabled": _safe_bool(row.get("encryption_enabled")), # Gate 2
            "access_control_enabled": _safe_bool(row.get("access_control_enabled")), # Gate 2
            "retention_policy_applied": _safe_bool(row.get("retention_policy_applied")), # Gate 2
            "data_processor_type": data_processor_type, # Gate 2, Technique 5
            "dpa_signed": dpa_signed, # Gate 2
            "dpa_expiry_date": dpa_expiry_date # Gate 2, Technique 2
        })
    return records
 
def _anonymize_policies(df: pd.DataFrame, tenant_id: str) -> List[dict]:
    records = []
    for index, row in df.iterrows():
        row_num = index + 2
        records.append({
            "policy_hash": _extract_hash(row, "policy_hash", "policy_id", tenant_id), # Gate 1, Technique 1
            "tenant_id": tenant_id, # Gate 1
            "policy_type": _validate_enum(row.get("policy_type"), ["retention", "consent", "encryption", "access_control", "breach_notification", "data_minimisation"], "policy_type", "policies.csv", row_num, required=("policy_type" in row)), # Gate 2, Technique 5
            "policy_name": None if ("policy_name" not in row) else (str(row["policy_name"]).strip() if (pd.notna(row.get("policy_name")) and str(row["policy_name"]).strip() not in ("", "None")) else None), # Gate 1
            "policy_value_numeric": int(float(row["policy_value_numeric"])) if pd.notna(row.get("policy_value_numeric")) else None, # Gate 2
            "policy_value_unit": _validate_enum(row.get("policy_value_unit"), ["days", "months", "years", "hours", "count"], "policy_value_unit", "policies.csv", row_num, required=False), # Gate 2, Technique 5
            "policy_value_text": (
                str(row["policy_value_text"]).strip()
                if pd.notna(row.get("policy_value_text"))
                and str(row["policy_value_text"]).strip().lower() not in ("", "none", "nan")
                else None
            ), # Required evidence for POLICY-002 and POLICY-003
            "effective_date": _truncate_to_date(row.get("effective_date")), # Gate 2, Technique 2
            "last_updated": _truncate_to_date(row.get("last_updated")), # Gate 2, Technique 2
            "is_active": _safe_bool(row.get("is_active")), # Gate 2
            "additional_attributes": (
                str(row["additional_attributes"])
                if pd.notna(row.get("additional_attributes"))
                else "{}"
            )
        })
    return records

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

class DsarValidationError(ValueError):
    def __init__(self, filename: str, row_number: int, field: str, error_code: str, explanation: str):
        self.filename = filename
        self.row_number = row_number
        self.field = field
        self.error_code = error_code
        self.explanation = explanation
        super().__init__(f"DSAR Validation error in {filename} at row {row_number}: {error_code} on field {field}. {explanation}")

def anonymize_dataframe(df: pd.DataFrame, table_name: str, tenant_id: str) -> Union[dict, List[dict]]:
    """
    Applies anonymization techniques based on the specific table's schema 
    and DPDP Act gate requirements. Routes to the correct table anonymizer.
    
    Returns:
        dict for governance_config (single-row tenant config)
        List[dict] for all other tables (multi-row datasets)
    """
    if df is None or df.empty:
        return {} if table_name == "governance_config" else []

    # Route to table-specific anonymizer
    dispatch = {
        "governance_config": _anonymize_governance_config,
        "customer_master": _anonymize_customer_master,
        "consent_records": _anonymize_consent_records,
        "transaction_events": _anonymize_transaction_events,
        "access_logs": _anonymize_access_logs,
        "data_lifecycle": _anonymize_data_lifecycle,
        "security_events": _anonymize_security_events,
        "dsar_requests": _anonymize_dsar_requests,
        "system_inventory": _anonymize_system_inventory,
        "policies": _anonymize_policies
    }

    if table_name not in dispatch:
        raise ValueError(f"Unknown table name for anonymization: {table_name}")

    return dispatch[table_name](df, tenant_id)
