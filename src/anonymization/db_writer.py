import os
import logging
import psycopg
from datetime import date, timedelta
from typing import Dict, Any
import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class CrossFileValidationError(ValueError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__(f"Cross-file validation failed: {errors}")

def get_db_connection() -> psycopg.Connection:
    """
    Establishes a connection to the PostgreSQL database using psycopg v3.
    Credentials are drawn from the environment variables.
    """
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "tenant_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres")
    )

def validate_cross_file_relationships(tenant_id: str, data: Dict[str, Any]) -> list[dict]:
    errors = []
    
    # Extract sets of existing hashes for quick lookup
    customer_hashes = {c["customer_hash"] for c in data.get("customer_master", []) if c.get("customer_hash")}
    consent_hashes = {c["consent_hash"] for c in data.get("consent_records", []) if c.get("consent_hash")}
    system_hashes = {s["system_hash"] for s in data.get("system_inventory", []) if s.get("system_hash")}
    
    # 1. consent_records -> customer_master
    if "customer_master" in data and "consent_records" in data:
        for idx, row in enumerate(data.get("consent_records", [])):
            cust_hash = row.get("customer_hash")
            if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                errors.append({
                    "source_file": "consent_records.csv",
                    "table": "consent_records",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": None,
                    "message": "Referenced customer is blank or null."
                })
            elif cust_hash not in customer_hashes:
                errors.append({
                    "source_file": "consent_records.csv",
                    "table": "consent_records",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": cust_hash,
                    "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                })
            
    # 2. transaction_events -> customer_master & consent_records & system_inventory (third_party_hash)
    if "transaction_events" in data:
        for idx, row in enumerate(data.get("transaction_events", [])):
            cust_hash = row.get("customer_hash")
            if "customer_master" in data:
                if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "customer_id",
                        "invalid_reference": None,
                        "message": "Referenced customer is blank or null."
                    })
                elif cust_hash not in customer_hashes:
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "customer_id",
                        "invalid_reference": cust_hash,
                        "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                    })
            
            con_hash = row.get("consent_hash")
            if "consent_records" in data:
                if not con_hash or str(con_hash).strip() == "" or str(con_hash).strip() == "None":
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "consent_id",
                        "invalid_reference": None,
                        "message": "Referenced consent is blank or null."
                    })
                elif con_hash not in consent_hashes:
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "consent_id",
                        "invalid_reference": con_hash,
                        "message": f"Referenced consent '{con_hash}' does not exist in consent_records.csv."
                    })
            
            tp_hash = row.get("third_party_hash")
            shared = row.get("shared_with_third_party")
            is_shared = False
            if shared is not None:
                if isinstance(shared, bool):
                    is_shared = shared
                else:
                    is_shared = str(shared).lower() in ["true", "1", "yes", "y", "t"]
            
            if is_shared:
                if not tp_hash or str(tp_hash).strip() == "" or str(tp_hash).strip() == "None":
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "third_party_id",
                        "invalid_reference": None,
                        "message": "Referenced third party system is blank or null but transaction is shared."
                    })
                elif "system_inventory" in data and tp_hash not in system_hashes:
                    errors.append({
                        "source_file": "transaction_events.csv",
                        "table": "transaction_events",
                        "row_number": idx + 2,
                        "field_name": "third_party_id",
                        "invalid_reference": tp_hash,
                        "message": f"Referenced third party system '{tp_hash}' does not exist in system_inventory.csv."
                    })
            else:
                if tp_hash and str(tp_hash).strip() != "" and str(tp_hash).strip() != "None":
                    if "system_inventory" in data and tp_hash not in system_hashes:
                        errors.append({
                            "source_file": "transaction_events.csv",
                            "table": "transaction_events",
                            "row_number": idx + 2,
                            "field_name": "third_party_id",
                            "invalid_reference": tp_hash,
                            "message": f"Referenced third party system '{tp_hash}' does not exist in system_inventory.csv."
                        })
            
    # 3. access_logs -> customer_master
    if "customer_master" in data and "access_logs" in data:
        for idx, row in enumerate(data.get("access_logs", [])):
            cust_hash = row.get("customer_hash")
            if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                errors.append({
                    "source_file": "access_logs.csv",
                    "table": "access_logs",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": None,
                    "message": "Referenced customer is blank or null."
                })
            elif cust_hash not in customer_hashes:
                errors.append({
                    "source_file": "access_logs.csv",
                    "table": "access_logs",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": cust_hash,
                    "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                })
            
            sys_hash = row.get("system_hash")
            if sys_hash and "system_inventory" in data and sys_hash not in system_hashes:
                errors.append({
                    "source_file": "access_logs.csv",
                    "table": "access_logs",
                    "row_number": idx + 2,
                    "field_name": "system_id",
                    "invalid_reference": sys_hash,
                    "message": f"Referenced system '{sys_hash}' does not exist in system_inventory.csv."
                })
            
    # 4. data_lifecycle -> customer_master
    if "customer_master" in data and "data_lifecycle" in data:
        for idx, row in enumerate(data.get("data_lifecycle", [])):
            cust_hash = row.get("customer_hash")
            if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                errors.append({
                    "source_file": "data_lifecycle.csv",
                    "table": "data_lifecycle",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": None,
                    "message": "Referenced customer is blank or null."
                })
            elif cust_hash not in customer_hashes:
                errors.append({
                    "source_file": "data_lifecycle.csv",
                    "table": "data_lifecycle",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": cust_hash,
                    "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                })
            
    # 5. security_events -> customer_master
    if "customer_master" in data and "security_events" in data:
        for idx, row in enumerate(data.get("security_events", [])):
            cust_hash = row.get("customer_hash")
            if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                errors.append({
                    "source_file": "security_events.csv",
                    "table": "security_events",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": None,
                    "message": "Referenced customer is blank or null."
                })
            elif cust_hash not in customer_hashes:
                errors.append({
                    "source_file": "security_events.csv",
                    "table": "security_events",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": cust_hash,
                    "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                })
            
    # 6. dsar_requests -> customer_master
    if "customer_master" in data and "dsar_requests" in data:
        for idx, row in enumerate(data.get("dsar_requests", [])):
            cust_hash = row.get("customer_hash")
            if not cust_hash or str(cust_hash).strip() == "" or str(cust_hash).strip() == "None":
                errors.append({
                    "source_file": "dsar_requests.csv",
                    "table": "dsar_requests",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": None,
                    "message": "Referenced customer is blank or null."
                })
            elif cust_hash not in customer_hashes:
                errors.append({
                    "source_file": "dsar_requests.csv",
                    "table": "dsar_requests",
                    "row_number": idx + 2,
                    "field_name": "customer_id",
                    "invalid_reference": cust_hash,
                    "message": f"Referenced customer '{cust_hash}' does not exist in customer_master.csv."
                })
            
    return errors

def write_tenant_data(tenant_id: str, data: Dict[str, Any]) -> Dict[str, int]:
    """
    Inserts mapped tenant data into the PostgreSQL database.
    """
    validation_errors = validate_cross_file_relationships(tenant_id, data)
    if validation_errors:
        raise CrossFileValidationError(validation_errors)

    rows_written = {
        "governance_config": 0,
        "system_inventory": 0,
        "policies": 0,
        "customer_master": 0,
        "consent_records": 0,
        "transaction_events": 0,
        "access_logs": 0,
        "data_lifecycle": 0,
        "security_events": 0,
        "dsar_requests": 0
    }
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                
                # ── [E-10 FIX] ATOMIC TENANT SLICE REPLACEMENT ─────────────────────────────
                # Delete all existing rows for this tenant before inserting fresh data.
                # Executed in FK-safe child-first order to respect foreign key constraints.
                # All DELETEs and subsequent INSERTs run in the same transaction — any
                # failure causes a full rollback, leaving the DB in its previous state.
                logger.info("[E-10] Purging existing data for tenant '%s' before re-ingestion.", tenant_id)
                for _table in [
                    "dsar_requests",
                    "security_events",
                    "data_lifecycle",
                    "access_logs",
                    "transaction_events",
                    "consent_records",
                    "customer_master",
                    "policies",
                    "system_inventory",
                    "governance_config",
                ]:
                    cur.execute(f"DELETE FROM {_table} WHERE tenant_id = %s", (tenant_id,))  # noqa: S608
                    logger.info("[E-10] Cleared %d rows from '%s' for tenant '%s'.", cur.rowcount, _table, tenant_id)
                # ── END PURGE ────────────────────────────────────────────────────────────────

                # 1. governance_config
                try:
                    gc = data.get("governance_config")
                    if gc:
                        cur.execute("""
                            INSERT INTO governance_config 
                            (tenant_id, tenant_name, grievance_endpoint_available, dpo_assigned, dpo_contact_masked,
                             audit_frequency_days, last_audit_date, risk_level) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            gc["tenant_id"], gc["tenant_name"], gc["grievance_endpoint_available"], 
                            gc["dpo_assigned"], gc.get("dpo_contact_masked"), gc["audit_frequency_days"],
                            gc["last_audit_date"], gc["risk_level"]
                        ))
                        rows_written["governance_config"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into governance_config: {e}")

                # 2. system_inventory
                try:
                    si_list = data.get("system_inventory", [])
                    if isinstance(si_list, dict):
                        si_list = [si_list]
                    for si in si_list:
                        cur.execute("""
                            INSERT INTO system_inventory 
                            (system_hash, tenant_id, system_name, system_type, pii_stored, encryption_enabled, 
                             access_control_enabled, data_processor_type, retention_policy_applied, 
                             dpa_signed, dpa_expiry_date) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            si["system_hash"], si["tenant_id"], si["system_name"], si["system_type"],
                            si.get("pii_stored", False), si["encryption_enabled"], si["access_control_enabled"],
                            si["data_processor_type"], si["retention_policy_applied"],
                            si["dpa_signed"], si["dpa_expiry_date"]
                        ))
                        rows_written["system_inventory"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into system_inventory: {e}")

                # 3. policies
                try:
                    pol_list = data.get("policies", [])
                    if isinstance(pol_list, dict):
                        pol_list = [pol_list]
                    for pol in pol_list:
                        cur.execute("""
                            INSERT INTO policies 
                            (policy_hash, tenant_id, policy_type, policy_name, policy_value_numeric, 
                             policy_value_unit, effective_date, last_updated, is_active) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            pol["policy_hash"], pol["tenant_id"], pol["policy_type"], pol["policy_name"], 
                            pol["policy_value_numeric"], pol["policy_value_unit"], pol["effective_date"], 
                            pol["last_updated"], pol["is_active"]
                        ))
                        rows_written["policies"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into policies: {e}")

                # 4. customer_master
                try:
                    cm_list = data.get("customer_master", [])
                    if isinstance(cm_list, dict):
                        cm_list = [cm_list]
                    for cm in cm_list:
                        cur.execute("""
                            INSERT INTO customer_master 
                            (customer_hash, tenant_id, is_minor, data_principal_type, account_status, 
                             kyc_status, country, created_at) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            cm["customer_hash"], cm["tenant_id"], cm["is_minor"], cm["data_principal_type"], 
                            cm["account_status"], cm["kyc_status"], cm["country"], cm["created_at"]
                        ))
                        rows_written["customer_master"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into customer_master: {e}")

                # 5. consent_records
                try:
                    cr_list = data.get("consent_records", [])
                    if isinstance(cr_list, dict):
                        cr_list = [cr_list]
                    for cr in cr_list:
                        cur.execute("""
                            INSERT INTO consent_records 
                            (consent_hash, customer_hash, tenant_id, consent_status, consent_date, 
                             expiry_date, withdrawal_date, consented_purpose, consent_version, notice_provided,
                             is_bundled, consent_channel, guardian_consent_hash, third_party_sharing_permitted)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            cr["consent_hash"], cr["customer_hash"], cr["tenant_id"], cr["consent_status"], 
                            cr["consent_date"], cr["expiry_date"], cr.get("withdrawal_date"), cr["consented_purpose"], 
                            cr["consent_version"], cr["notice_provided"], cr["is_bundled"], 
                            cr["consent_channel"], cr["guardian_consent_hash"], cr.get("third_party_sharing_permitted")
                        ))
                        rows_written["consent_records"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into consent_records: {e}")

                # 6. transaction_events
                try:
                    for tx in data.get("transaction_events", []):
                        event_hash = tx["event_hash"]
                        tenant_for_tx = tx["tenant_id"]
                        cur.execute("""
                            INSERT INTO transaction_events 
                            (event_hash, customer_hash, tenant_id, consent_hash, event_type, 
                             processing_purpose, event_date, shared_with_third_party, 
                             third_party_hash, is_cross_border, transfer_country) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            event_hash, tx["customer_hash"], tenant_for_tx, tx["consent_hash"],
                            tx["event_type"], tx["processing_purpose"], tx["event_date"],
                            tx["shared_with_third_party"], tx["third_party_hash"],
                            tx["is_cross_border"], tx["transfer_country"]
                        ))
                        rows_written["transaction_events"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into transaction_events: {e}")

                # 7. access_logs
                try:
                    for al in data.get("access_logs", []):
                        cur.execute("""
                            INSERT INTO access_logs 
                            (access_hash, customer_hash, tenant_id, employee_hash, employee_role, 
                             accessed_pii, pii_fields_accessed, access_reason, access_outcome, 
                             data_volume_accessed, access_date, system_hash, pii_fields_justified) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            al["access_hash"], al["customer_hash"], al["tenant_id"], al["employee_hash"], 
                            al["employee_role"], al["accessed_pii"], al["pii_fields_accessed"], 
                            al["access_reason"], al["access_outcome"], al["data_volume_accessed"], 
                            al["access_date"], al.get("system_hash"), al.get("pii_fields_justified")
                        ))
                        rows_written["access_logs"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into access_logs: {e}")

                # 8. data_lifecycle
                try:
                    dl_list = data.get("data_lifecycle", [])
                    if isinstance(dl_list, dict):
                        dl_list = [dl_list]
                    for dl in dl_list:
                        cur.execute("""
                            INSERT INTO data_lifecycle 
                            (lifecycle_hash, customer_hash, tenant_id, data_category, 
                             retention_expiry_date, retention_status, purpose_completed, 
                             erasure_requested, erasure_date, legal_hold_flag, erasure_request_source) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            dl["lifecycle_hash"], dl["customer_hash"], dl["tenant_id"], dl["data_category"], 
                            dl["retention_expiry_date"], dl["retention_status"], dl["purpose_completed"], 
                            dl["erasure_requested"], dl["erasure_date"], dl["legal_hold_flag"], 
                            dl["erasure_request_source"]
                        ))
                        rows_written["data_lifecycle"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into data_lifecycle: {e}")

                # 9. security_events
                try:
                    for se in data.get("security_events", []):
                        cur.execute("""
                            INSERT INTO security_events 
                            (security_hash, customer_hash, tenant_id, pii_encrypted, encryption_type, 
                             breach_detected, breach_confirmed_date, notification_delay_hours, 
                             affected_user_count, data_categories_breached, security_audit_flag) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            se["security_hash"], se["customer_hash"], se["tenant_id"], se["pii_encrypted"], 
                            se["encryption_type"], se["breach_detected"], se["breach_confirmed_date"], 
                            se["notification_delay_hours"], se["affected_user_count"], 
                            se["data_categories_breached"], se["security_audit_flag"]
                        ))
                        rows_written["security_events"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into security_events: {e}")

                # 10. dsar_requests
                try:
                    for dsar in data.get("dsar_requests", []):
                        cur.execute("""
                            INSERT INTO dsar_requests 
                            (dsar_hash, customer_hash, tenant_id, request_type, submitted_date, 
                             acknowledged_date, sla_due_date, sla_breached, fulfilled_date, 
                             fulfillment_status, rejection_reason) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            dsar["dsar_hash"], dsar["customer_hash"], dsar["tenant_id"], dsar["request_type"], 
                            dsar["submitted_date"], dsar["acknowledged_date"], dsar["sla_due_date"],
                            dsar["sla_breached"], dsar["fulfilled_date"], dsar["fulfillment_status"], 
                            dsar["rejection_reason"]
                        ))
                        rows_written["dsar_requests"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into dsar_requests: {e}")

            # Commit the transaction completely
            conn.commit()

            # Log ingestion row counts (no PII)
            for table_name, count in rows_written.items():
                logger.info(f"[INGESTION] {table_name}: inserted={count}")
            
    except Exception as e:
        # Implicit rollback occurs upon escaping the context manager with an error in psycopg3
        raise Exception(f"Transaction failed and aborted completely. Reason: {e}")

    return rows_written

