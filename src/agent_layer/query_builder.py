import logging

logger = logging.getLogger(__name__)

# DPDP-006 requires custom multi-join logic because it joins consent_records on consent_id
# and system_inventory on third_party_id, but rules table only holds one join_key ("consent_id").
NATIVE_QUERIES = {
    "DPDP-005": """
        SELECT 
            COALESCE(cr.consent_hash, c.customer_hash) AS primary_hash,
            c.*, 
            cr.consent_hash, cr.consent_status, cr.guardian_consent_hash,
            gr.consent_status AS guardian_consent_status
        FROM customer_master c
        LEFT JOIN consent_records cr ON c.customer_hash = cr.customer_hash AND c.tenant_id = cr.tenant_id
        LEFT JOIN consent_records gr ON cr.guardian_consent_hash = gr.consent_hash AND c.tenant_id = gr.tenant_id
        WHERE c.tenant_id = %s
    """,
    "DPDP-006": """
        SELECT p.*, cr.*, si.*
        FROM transaction_events p
        LEFT JOIN consent_records cr ON p.consent_hash = cr.consent_hash AND p.tenant_id = cr.tenant_id
        LEFT JOIN system_inventory si ON p.third_party_hash = si.system_hash AND p.tenant_id = si.tenant_id
        WHERE p.tenant_id = %s
    """,
    "DPDP-007": """
        SELECT p.*, si.*
        FROM access_logs p
        LEFT JOIN system_inventory si ON si.system_hash = p.system_hash AND si.tenant_id = p.tenant_id
        WHERE p.tenant_id = %s
    """,
    "DPDP-008": """
        SELECT p.*
        FROM security_events p
        WHERE p.tenant_id = %s
    """,
    "DPDP-010": """
        SELECT p.*,
               CASE WHEN dl.has_active_retention THEN 'not_deleted' ELSE 'deleted' END AS retention_status,
               dl.has_legal_hold AS legal_hold_flag
        FROM dsar_requests p
        LEFT JOIN LATERAL (
            SELECT 
                EXISTS (
                    SELECT 1 FROM data_lifecycle d 
                    WHERE d.customer_hash = p.customer_hash 
                      AND d.tenant_id = p.tenant_id 
                      AND d.retention_status <> 'deleted'
                ) AS has_active_retention,
                EXISTS (
                    SELECT 1 FROM data_lifecycle d 
                    WHERE d.customer_hash = p.customer_hash 
                      AND d.tenant_id = p.tenant_id 
                      AND d.legal_hold_flag = true
                ) AS has_legal_hold
        ) dl ON true
        WHERE p.tenant_id = %s
    """,
    "DPDP-012": """
        SELECT g.*,
               CASE
                   WHEN EXISTS (
                       SELECT 1
                       FROM access_logs a
                       WHERE a.tenant_id = g.tenant_id
                         AND a.access_outcome IS NULL
                   )
                   THEN NULL
                   ELSE 'complete'
               END AS access_outcome
        FROM governance_config g
        WHERE g.tenant_id = %s
    """,
    "DPDP-015": """
        SELECT p.*, si.*
        FROM transaction_events p
        LEFT JOIN system_inventory si ON p.third_party_hash = si.system_hash AND p.tenant_id = si.tenant_id
        WHERE p.tenant_id = %s
    """
}

def build_query(rule: dict, tenant_id: str) -> tuple[str, list]:
    """
    Build a parameterized SQL query from a rule's metadata.
    """
    rule_id = rule.get("rule_id")
    
    if rule_id in NATIVE_QUERIES:
        return NATIVE_QUERIES[rule_id], [tenant_id]
        
    primary_table = rule.get("primary_table")
    join_tables = rule.get("join_tables", [])
    join_key = rule.get("join_key")
    
    if join_key and join_key.endswith('_id') and join_key != 'tenant_id':
        join_key = join_key.replace('_id', '_hash')
    
    select_clause = "SELECT p.*"
    from_clause = f"FROM {primary_table} p"
    join_clauses = []
    
    if join_tables and join_key:
        for i, table in enumerate(join_tables):
            # Assign short alias
            alias = f"{table[:2]}{i}"
            select_clause += f", {alias}.*"
            join_clauses.append(f"LEFT JOIN {table} {alias} ON p.{join_key} = {alias}.{join_key} AND p.tenant_id = {alias}.tenant_id")
            
    sql_parts = [select_clause, from_clause]
    sql_parts.extend(join_clauses)
    sql_parts.append("WHERE p.tenant_id = %s")
    
    sql = " ".join(sql_parts)
    return sql, [tenant_id]
