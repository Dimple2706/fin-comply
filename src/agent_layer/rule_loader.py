import logging
import json

logger = logging.getLogger(__name__)

def load_rules(agent_name: str, conn) -> list[dict]:
    """
    Fetch active rules from the database for a given agent.
    """
    query = """
        SELECT r.*, c.max_penalty_crore 
        FROM rules r
        JOIN clauses c ON r.clause_id = c.clause_id
        WHERE r.assigned_agent = %s AND r.enabled = TRUE 
        ORDER BY r.rule_id
    """
    try:
        rows = conn.execute(query, [agent_name]).fetchall()
        
        results = []
        for r in rows:
            rule_dict = dict(r)
            
            # Ensure evidence_signals is a list of dicts
            signals = rule_dict.get('evidence_signals')
            if isinstance(signals, str):
                try:
                    rule_dict['evidence_signals'] = json.loads(signals)
                except json.JSONDecodeError:
                    rule_dict['evidence_signals'] = []
            
            # Same for join_tables if needed
            join_tables = rule_dict.get('join_tables')
            if isinstance(join_tables, str):
                try:
                    rule_dict['join_tables'] = json.loads(join_tables)
                except json.JSONDecodeError:
                    rule_dict['join_tables'] = []
                    
            results.append(rule_dict)
            
        return results
    except Exception as e:
        logger.error(f"Failed to load rules for {agent_name}: {e}")
        return []
