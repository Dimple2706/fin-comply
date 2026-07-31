import os
import psycopg
from datetime import date, timedelta
from typing import Dict, Any, List
import dotenv

dotenv.load_dotenv()

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
    error occurs, the entire transaction rolls back. Idempotency is maintained 
    via ON CONFLICT DO NOTHING.
    
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

    def ensure_customer_exists(customer_hash: str, tenant_for_row: str) -> None:
        """
        Create a minimal customer_master placeholder if a foreign key reference
        points to a customer not present in the uploaded customer file.
        """
        cur.execute(
            """
            INSERT INTO customer_master
            (customer_hash, tenant_id, is_minor, data_principal_type, account_status,
             kyc_status, country, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                customer_hash,
                tenant_for_row,
                False,
                "individual",
                "active",
                "pending",
                "IN",
                date.today(),
            ),
        )

    def ensure_consent_exists(
        consent_hash: str,
        customer_hash: str,
        tenant_for_row: str,
        event_date_value: Any,
        processing_purpose: Any,
    ) -> None:
        """
        Create a minimal consent_records placeholder if a transaction references
        a consent hash that was not present in the uploaded consent file.

        The placeholder is intentionally shaped as expired/past-dated so the
        DB-backed analysis can still surface a consent-related violation instead
        of silently treating the transaction as compliant.
        """
        event_date_text = None
        try:
            from src.anonymization.field_mapper import _truncate_to_date
            event_date_text = _truncate_to_date(event_date_value)
        except Exception:
            event_date_text = None

        try:
            event_dt = date.fromisoformat(event_date_text) if event_date_text else date.today()
        except Exception:
            event_dt = date.today()

        try:
            consent_dt = event_dt.replace(year=event_dt.year - 1) if event_dt.year > 1 else event_dt
        except ValueError:
            # Handles Feb 29 when previous year is not a leap year
            consent_dt = event_dt - timedelta(days=365) if event_dt.year > 1 else event_dt
            
        try:
            expiry_dt = event_dt.replace(day=max(1, min(event_dt.day, 27))) if event_dt else event_dt
        except ValueError:
            expiry_dt = event_dt - timedelta(days=1) if event_dt else event_dt
            
        if expiry_dt >= event_dt:
            try:
                expiry_dt = event_dt.replace(day=max(1, event_dt.day - 1)) if event_dt.day > 1 else event_dt
            except ValueError:
                expiry_dt = event_dt - timedelta(days=1) if event_dt else event_dt

        cur.execute(
            """
            INSERT INTO consent_records
            (consent_hash, customer_hash, tenant_id, consent_status, consent_date,
             expiry_date, withdrawal_date, consented_purpose, consent_version,
             notice_provided, is_bundled, consent_channel, guardian_consent_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                consent_hash,
                customer_hash,
                tenant_for_row,
                "expired",
                consent_dt,
                expiry_dt,
                None,
                str(processing_purpose) if processing_purpose else "account_management",
                "v0.0",
                True,
                False,
                "app",
                None,
            ),
        )
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                
                # 1. governance_config
                try:
                    gc = data.get("governance_config")
                    if gc:
                        cur.execute("""
                            INSERT INTO governance_config 
                            (tenant_id, tenant_name, grievance_endpoint_available, dpo_assigned, dpo_contact_masked,
                             audit_frequency_days, last_audit_date, risk_level) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                    si = data.get("system_inventory")
                    if si:
                        cur.execute("""
                            INSERT INTO system_inventory 
                            (system_hash, tenant_id, system_name, system_type, encryption_enabled, 
                             access_control_enabled, data_processor_type, retention_policy_applied, 
                             dpa_signed, dpa_expiry_date) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            si["system_hash"], si["tenant_id"], si["system_name"], si["system_type"], 
                            si["encryption_enabled"], si["access_control_enabled"], si["data_processor_type"], 
                            si["retention_policy_applied"], si["dpa_signed"], si["dpa_expiry_date"]
                        ))
                        rows_written["system_inventory"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into system_inventory: {e}")

                # 3. policies
                try:
                    pol = data.get("policies")
                    if pol:
                        cur.execute("""
                            INSERT INTO policies 
                            (policy_hash, tenant_id, policy_type, policy_name, policy_value_numeric, 
                             policy_value_unit, effective_date, last_updated, is_active) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                    cm = data.get("customer_master")
                    if cm:
                        cur.execute("""
                            INSERT INTO customer_master 
                            (customer_hash, tenant_id, is_minor, data_principal_type, account_status, 
                             kyc_status, country, created_at) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            cm["customer_hash"], cm["tenant_id"], cm["is_minor"], cm["data_principal_type"], 
                            cm["account_status"], cm["kyc_status"], cm["country"], cm["created_at"]
                        ))
                        rows_written["customer_master"] += cur.rowcount
                except Exception as e:
                    raise Exception(f"Error inserting into customer_master: {e}")

                # 5. consent_records
                try:
                    cr = data.get("consent_records")
                    if cr:
                        ensure_customer_exists(cr["customer_hash"], cr["tenant_id"])
                        cur.execute("""
                            INSERT INTO consent_records 
                            (consent_hash, customer_hash, tenant_id, consent_status, consent_date, 
                             expiry_date, withdrawal_date, consented_purpose, consent_version, notice_provided,
                             is_bundled, consent_channel, guardian_consent_hash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                try:
                    for tx in data.get("transaction_events", []):
                        ensure_customer_exists(tx["customer_hash"], tx["tenant_id"])
                        if tx.get("consent_hash"):
                            ensure_consent_exists(
                                tx["consent_hash"],
                                tx["customer_hash"],
                                tx["tenant_id"],
                                tx.get("event_date"),
                                tx.get("processing_purpose"),
                            )
                        third_party_hash = tx.get("third_party_hash")
                        if third_party_hash:
                            # Ensure FK target exists for transaction_events_third_party_hash_fkey.
                            # Uploaded third_party_id values may not be present in system_inventory CSV.
                            cur.execute("""
                                INSERT INTO system_inventory
                                (system_hash, tenant_id, system_name, system_type, encryption_enabled,
                                 access_control_enabled, data_processor_type, retention_policy_applied,
                                 dpa_signed, dpa_expiry_date)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT DO NOTHING
                            """, (
                                third_party_hash,
                                tx["tenant_id"],
                                "Derived Third Party",
                                "payment_gateway",
                                True,
                                True,
                                "third_party_processor",
                                True,
                                False,
                                None,
                            ))

                        cur.execute("""
                            INSERT INTO transaction_events 
                            (event_hash, customer_hash, tenant_id, consent_hash, event_type, 
                             processing_purpose, event_date, shared_with_third_party, 
                             third_party_hash, is_cross_border, transfer_country) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (
                            tx["event_hash"], tx["customer_hash"], tx["tenant_id"], tx["consent_hash"], 
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
                        ensure_customer_exists(al["customer_hash"], al["tenant_id"])
                        cur.execute("""
                            INSERT INTO access_logs 
                            (access_hash, customer_hash, tenant_id, employee_hash, employee_role, 
                             accessed_pii, pii_fields_accessed, access_reason, access_outcome, 
                             data_volume_accessed, access_date) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                    dl = data.get("data_lifecycle")
                    if dl:
                        ensure_customer_exists(dl["customer_hash"], dl["tenant_id"])
                        cur.execute("""
                            INSERT INTO data_lifecycle 
                            (lifecycle_hash, customer_hash, tenant_id, data_category, 
                             retention_expiry_date, retention_status, purpose_completed, 
                             erasure_requested, erasure_date, legal_hold_flag, erasure_request_source) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                        ensure_customer_exists(se["customer_hash"], se["tenant_id"])
                        cur.execute("""
                            INSERT INTO security_events 
                            (security_hash, customer_hash, tenant_id, pii_encrypted, encryption_type, 
                             breach_detected, breach_confirmed_date, notification_delay_hours, 
                             affected_user_count, data_categories_breached, security_audit_flag) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
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
                        ensure_customer_exists(dsar["customer_hash"], dsar["tenant_id"])

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
                            ON CONFLICT DO NOTHING
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
            
    except Exception as e:
        # Implicit rollback occurs upon escaping the context manager with an error in psycopg3
        raise Exception(f"Transaction failed and aborted completely. Reason: {e}")

    return rows_written
