import logging

logger = logging.getLogger(__name__)

# DPDP-006 requires custom multi-join logic because it joins consent_records on consent_id
# and system_inventory on third_party_id, but rules table only holds one join_key ("consent_id").
NATIVE_QUERIES = {
    "DPDP-006": """
        SELECT p.*, cr.*, si.*
        FROM transaction_events p
        LEFT JOIN consent_records cr ON p.consent_hash = cr.consent_hash
        LEFT JOIN system_inventory si ON p.third_party_hash = si.system_hash
        WHERE p.tenant_id = %s
    """,
    "DPDP-007": """
        SELECT p.*, si.*
        FROM access_logs p
        LEFT JOIN system_inventory si ON p.tenant_id = si.tenant_id
        WHERE p.tenant_id = %s
    """,
    "DPDP-008": """
        SELECT p.*, si.*
        FROM security_events p
        LEFT JOIN system_inventory si ON p.tenant_id = si.tenant_id
        WHERE p.tenant_id = %s
    """,
    "DPDP-015": """
        SELECT p.*, si.*
        FROM transaction_events p
        LEFT JOIN system_inventory si ON p.third_party_hash = si.system_hash
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
            join_clauses.append(f"LEFT JOIN {table} {alias} ON p.{join_key} = {alias}.{join_key}")
            
    sql_parts = [select_clause, from_clause]
    sql_parts.extend(join_clauses)
    sql_parts.append("WHERE p.tenant_id = %s")
    
    sql = " ".join(sql_parts)
    return sql, [tenant_id]
