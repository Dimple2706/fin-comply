import logging
import datetime

logger = logging.getLogger(__name__)

# PART A — NATIVE_EVALUATORS dict
NATIVE_EVALUATORS = {}

def register_native(rule_id, signal_id):
    def decorator(fn):
        NATIVE_EVALUATORS[(rule_id, signal_id)] = fn
        return fn
    return decorator

# PART B — evaluate_signal function
def evaluate_signal(rule_id, signal_id, signal_def, row: dict) -> bool:
    if (rule_id, signal_id) in NATIVE_EVALUATORS:
        return NATIVE_EVALUATORS[(rule_id, signal_id)](row)
        
    operator = signal_def.get('operator')
    field = signal_def.get('field')
    value = signal_def.get('value')
    
    # Handle known schema mappings from rules JSON
    if field == 'expiry_timestamp' and 'expiry_date' in row:
        field = 'expiry_date'
        
    if field not in row and operator not in ('is_null', 'is_not_null'):
        logger.warning(f"Field '{field}' not found in row for rule {rule_id}, signal {signal_id}")
        return False
        
    try:
        row_val = row.get(field)
        
        # Resolve target value if it refers to another column in the row
        target_val = value
        if isinstance(target_val, str) and target_val in row:
            target_val = row[target_val]
            
        if operator == 'in':
            if row_val is None or target_val is None:
                return False
            return row_val in target_val
            
        elif operator == 'not_in':
            if row_val is None or target_val is None:
                return False
            return row_val not in target_val
            
        elif operator == 'equals':
            if isinstance(target_val, bool):
                if isinstance(row_val, str):
                    row_val = row_val.lower() in ('true', 't', '1', 'yes', 'y')
                elif isinstance(row_val, int):
                    row_val = bool(row_val)
            return row_val == target_val
            
        elif operator == 'not_matches':
            return row_val != target_val
            
        elif operator == 'is_null':
            return row_val is None or row_val == ''
            
        elif operator == 'is_not_null':
            return row_val is not None and row_val != ''
            
        elif operator == 'less_than':
            if row_val is None or target_val is None:
                return False
                
            try:
                if isinstance(row_val, (str, datetime.date)) and isinstance(target_val, (str, datetime.date)):
                    v1 = row_val
                    v2 = target_val
                    if isinstance(v1, str):
                        v1 = datetime.date.fromisoformat(v1.split('T')[0])
                    if isinstance(v2, str):
                        v2 = datetime.date.fromisoformat(v2.split('T')[0])
                    return v1 < v2
            except (ValueError, AttributeError):
                pass
            return row_val < target_val
            
        elif operator == 'less_than_today':
            if row_val is None:
                return False
            try:
                v1 = row_val
                if isinstance(v1, str):
                    v1 = datetime.date.fromisoformat(v1.split('T')[0])
                if isinstance(v1, datetime.datetime):
                    v1 = v1.date()
                return v1 < datetime.date.today()
            except (ValueError, AttributeError):
                return False
                
        elif operator == 'greater_than':
            if row_val is None or value is None:
                return False
            try:
                v1 = float(row_val)
                v2 = float(value)
                return v1 > v2
            except (ValueError, TypeError):
                return row_val > value
                
        elif operator == 'not_contains':
            if row_val is None:
                return False
            return str(value) not in str(row_val)
            
        elif operator == 'exceeds_threshold_days':
            if row_val is None:
                return False
            threshold_field = value
            if threshold_field not in row or row[threshold_field] is None:
                return False
            try:
                v1 = row_val
                if isinstance(v1, str):
                    v1 = datetime.date.fromisoformat(v1.split('T')[0])
                if isinstance(v1, datetime.datetime):
                    v1 = v1.date()
                threshold = int(row[threshold_field])
                return (datetime.date.today() - v1).days > threshold
            except (ValueError, AttributeError, TypeError):
                return False
                
        elif operator == 'is_outdated':
            if row_val is None:
                return False
            target_field = value
            if target_field not in row or row[target_field] is None:
                return False
            return str(row_val) < str(row[target_field])
            
        else:
            logger.warning(f"Unrecognized operator '{operator}' for rule {rule_id}, signal {signal_id}")
            return False
            
    except Exception as e:
        logger.warning(f"Evaluation failed for rule {rule_id}, signal {signal_id}: {e}")
        return False

# PART C — evaluate_all_signals function
def evaluate_all_signals(rule_id, signals: list[dict], row: dict) -> dict[str, bool]:
    results = {}
    for s in signals:
        signal_id = s.get('signal_id')
        if not signal_id:
            continue
        results[signal_id] = evaluate_signal(rule_id, signal_id, s, row)
    return results
