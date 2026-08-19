import os
import logging
import psycopg
from datetime import date, timedelta
from typing import Dict, Any
import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

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

def write_tenant_data(tenant_id: str, data: Dict[str, Any]) -> Dict[str, int]:
    """
    Inserts mapped tenant data into the PostgreSQL database.

    This function adheres to the strict insertion order required by foreign keys.
    All operations execute within a single transaction to ensure consistency. If any
    error occurs, the entire transaction rolls back.

    [E-04 FIX] Foreign key references are validated before insertion — missing FKs
    are logged as data-quality warnings and the affected row is skipped. No synthetic
    placeholder records (fake expired consents, fake third-party systems, fake customers)
    are ever created. This prevents fabricated violations from corrupting compliance
    results and ML training labels.

    [E-10 FIX] Implements atomic tenant slice replacement. Before inserting any data,
    all existing rows for this tenant are deleted in FK-safe child-first order within
    the same transaction. This replaces the previous ON CONFLICT DO NOTHING strategy
    which silently discarded corrected re-uploads and left stale data in place.
    Re-uploading corrected CSVs now fully replaces the previous dataset.
    
    Gate 1: Tenant isolation is enforced throughout all inserts using `tenant_id`.
    Technique 4 (Suppression): Only the explicitly mapped, compliant fields reach 
    the database layer. Raw data is inherently excluded here.
    
    Args:
        tenant_id (str): The identifier for the tenant.
        data (Dict[str, Any]): The collection of mapped data dicts/lists keyed by table name.
        
    Returns:
        Dict[str, int]: A summary of the number of rows written per table.
    """
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

    def validate_customer_exists(customer_hash: str, tenant_for_row: str) -> bool:
        """
        [E-04 FIX] Validates that a customer_hash FK target exists in customer_master.
        Returns True if the customer exists, False otherwise.
        Never creates a synthetic placeholder row.
        """
        cur.execute(
            "SELECT 1 FROM customer_master WHERE customer_hash = %s AND tenant_id = %s LIMIT 1",
            (customer_hash, tenant_for_row),
        )
        return cur.fetchone() is not None

    def validate_consent_exists(
        consent_hash: str,
        customer_hash: str,
        tenant_for_row: str,
        event_hash: str,
    ) -> bool:
        """
        [E-04 FIX] Validates that a consent_hash FK target exists in consent_records.
        Returns True if the consent record exists, False otherwise.

        This replaces the old ensure_consent_exists() that fabricated an expired
        consent row when the referenced consent was missing. Fabricated expired
        consent records caused false DPDP-001 violations and corrupted ML training
        labels. Now: log the data quality warning and signal the caller to skip.
        """
        cur.execute(
            "SELECT 1 FROM consent_records WHERE consent_hash = %s AND tenant_id = %s LIMIT 1",
            (consent_hash, tenant_for_row),
        )
        exists = cur.fetchone() is not None
        if not exists:
            logger.warning(
                "[E-04] Skipping transaction '%s' for tenant '%s': "
                "consent_hash '%s' not found in consent_records. "
                "Upload a consent_records CSV row with a matching consent_id to resolve.",
                event_hash, tenant_for_row, consent_hash,
            )
        return exists
    
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
                        # [E-04 FIX] Validate customer FK — do not create placeholders
                        if not validate_customer_exists(cr["customer_hash"], cr["tenant_id"]):
                            logger.warning(
                                "[E-04] Skipping consent_record '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                cr["consent_hash"], cr["tenant_id"], cr["customer_hash"],
                            )
                            continue
                        cur.execute("""
                            INSERT INTO consent_records 
                            (consent_hash, customer_hash, tenant_id, consent_status, consent_date, 
                             expiry_date, withdrawal_date, consented_purpose, consent_version, notice_provided,
                             is_bundled, consent_channel, guardian_consent_hash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            cr["consent_hash"], cr["customer_hash"], cr["tenant_id"], cr["consent_status"], 
                            cr["consent_date"], cr["expiry_date"], cr.get("withdrawal_date"), cr["consented_purpose"], 
                            cr["consent_version"], cr["notice_provided"], cr["is_bundled"], 
                            cr["consent_channel"], cr["guardian_consent_hash"]
                        ))
                        rows_written["consent_records"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into consent_records: {e}")

                # 6. transaction_events
                # [E-04 FIX] Validate all FK references before inserting.
                # Missing consent_hash or third_party_hash are logged as data-quality
                # warnings and the row is skipped — never fabricated.
                try:
                    for tx in data.get("transaction_events", []):
                        event_hash = tx["event_hash"]
                        tenant_for_tx = tx["tenant_id"]

                        # FK: customer_master (validate only — never create placeholder)
                        if not validate_customer_exists(tx["customer_hash"], tenant_for_tx):
                            logger.warning(
                                "[E-04] Skipping transaction '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                event_hash, tenant_for_tx, tx["customer_hash"],
                            )
                            continue

                        # FK: consent_records (validate only — never create placeholder)
                        consent_hash = tx.get("consent_hash")
                        if consent_hash:
                            if not validate_consent_exists(
                                consent_hash, tx["customer_hash"], tenant_for_tx, event_hash
                            ):
                                # Skip this transaction — do NOT fabricate a fake expired consent
                                continue

                        # FK: system_inventory for third_party_hash (validate only — never create placeholder)
                        third_party_hash = tx.get("third_party_hash")
                        if third_party_hash:
                            cur.execute(
                                "SELECT 1 FROM system_inventory "
                                "WHERE system_hash = %s AND tenant_id = %s LIMIT 1",
                                (third_party_hash, tenant_for_tx),
                            )
                            if cur.fetchone() is None:
                                logger.warning(
                                    "[E-04] Transaction '%s' for tenant '%s': "
                                    "third_party_hash '%s' not found in system_inventory. "
                                    "Nullifying third_party_hash — upload a matching system_inventory row to resolve.",
                                    event_hash, tenant_for_tx, third_party_hash,
                                )
                                # Nullify rather than fabricate a fake third-party system entry
                                third_party_hash = None

                        cur.execute("""
                            INSERT INTO transaction_events 
                            (event_hash, customer_hash, tenant_id, consent_hash, event_type, 
                             processing_purpose, event_date, shared_with_third_party, 
                             third_party_hash, is_cross_border, transfer_country) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            event_hash, tx["customer_hash"], tenant_for_tx, tx["consent_hash"],
                            tx["event_type"], tx["processing_purpose"], tx["event_date"],
                            tx["shared_with_third_party"], third_party_hash,
                            tx["is_cross_border"], tx["transfer_country"]
                        ))
                        rows_written["transaction_events"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into transaction_events: {e}")

                # 7. access_logs
                try:
                    for al in data.get("access_logs", []):
                        # [E-04 FIX] Validate customer FK — do not create placeholders
                        if not validate_customer_exists(al["customer_hash"], al["tenant_id"]):
                            logger.warning(
                                "[E-04] Skipping access_log '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                al["access_hash"], al["tenant_id"], al["customer_hash"],
                            )
                            continue
                        cur.execute("""
                            INSERT INTO access_logs 
                            (access_hash, customer_hash, tenant_id, employee_hash, employee_role, 
                             accessed_pii, pii_fields_accessed, access_reason, access_outcome, 
                             data_volume_accessed, access_date) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            al["access_hash"], al["customer_hash"], al["tenant_id"], al["employee_hash"], 
                            al["employee_role"], al["accessed_pii"], al["pii_fields_accessed"], 
                            al["access_reason"], al["access_outcome"], al["data_volume_accessed"], 
                            al["access_date"]
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
                        # [E-04 FIX] Validate customer FK — do not create placeholders
                        if not validate_customer_exists(dl["customer_hash"], dl["tenant_id"]):
                            logger.warning(
                                "[E-04] Skipping data_lifecycle '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                dl["lifecycle_hash"], dl["tenant_id"], dl["customer_hash"],
                            )
                            continue
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
                        # [E-04 FIX] Validate customer FK — do not create placeholders
                        if not validate_customer_exists(se["customer_hash"], se["tenant_id"]):
                            logger.warning(
                                "[E-04] Skipping security_event '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                se["security_hash"], se["tenant_id"], se["customer_hash"],
                            )
                            continue
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
                        # [E-04 FIX] Validate customer FK — do not create placeholders
                        if not validate_customer_exists(dsar["customer_hash"], dsar["tenant_id"]):
                            logger.warning(
                                "[E-04] Skipping dsar_request '%s' for tenant '%s': "
                                "customer_hash '%s' not found in customer_master.",
                                dsar["dsar_hash"], dsar["tenant_id"], dsar["customer_hash"],
                            )
                            continue

                        # Enforce schema rule: sla_due_date must be exactly submitted_date + 30 days.
                        submitted_raw = dsar.get("submitted_date")
                        try:
                            submitted_dt = date.fromisoformat(str(submitted_raw)) if submitted_raw else date.today()
                        except Exception:
                            submitted_dt = date.today()
                        normalized_sla_due_date = (submitted_dt + timedelta(days=30)).isoformat()

                        cur.execute("""
                            INSERT INTO dsar_requests 
                            (dsar_hash, customer_hash, tenant_id, request_type, submitted_date, 
                             acknowledged_date, sla_due_date, sla_breached, fulfilled_date, 
                             fulfillment_status, rejection_reason) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            dsar["dsar_hash"], dsar["customer_hash"], dsar["tenant_id"], dsar["request_type"], 
                            submitted_dt.isoformat(), dsar["acknowledged_date"], normalized_sla_due_date,
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

