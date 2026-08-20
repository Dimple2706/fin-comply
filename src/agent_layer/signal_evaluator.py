import logging
import datetime

import json
logger = logging.getLogger(__name__)

# PART A â€” NATIVE_EVALUATORS dict
NATIVE_EVALUATORS = {}

def register_native(rule_id, signal_id):
    def decorator(fn):
        NATIVE_EVALUATORS[(rule_id, signal_id)] = fn
        return fn
    return decorator

@register_native('DPDP-005', 'guardian_consent_missing_or_invalid')
def _eval_dpdp_005(row: dict) -> bool:
    is_minor = row.get("is_minor", False)
    if isinstance(is_minor, str):
        is_minor = is_minor.lower() in ('true', 't', '1', 'yes', 'y')
    else:
        is_minor = bool(is_minor)

    if not is_minor:
        return False
        
    guardian_consent = row.get("guardian_consent_hash")
    consent_status = row.get("consent_status")

    if not guardian_consent:
        return True

    if consent_status != "active":
        return True

    return False

# PART B â€” evaluate_signal function
def evaluate_signal(rule_id, signal_id, signal_def, row: dict) -> bool:
    if (rule_id, signal_id) in NATIVE_EVALUATORS:
        return NATIVE_EVALUATORS[(rule_id, signal_id)](row)
        
    operator = signal_def.get('operator')
    field = signal_def.get('field')
    value = signal_def.get('value')
    
    # Handle known schema mappings from rules JSON
    if field == 'expiry_timestamp' and 'expiry_date' in row:
        field = 'expiry_date'
        
    # If the field is not a normal column, try additional_attributes JSONB.
    if field not in row:
        attrs = row.get("additional_attributes")

        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}

        if isinstance(attrs, dict) and field in attrs:
            row = dict(row)
            row[field] = attrs[field]

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
                date_types = (str, datetime.date, datetime.datetime)

                if isinstance(row_val, date_types) and isinstance(target_val, date_types):
                    def to_date(v):
                        if isinstance(v, datetime.datetime):
                            return v.date()
                        if isinstance(v, datetime.date):
                            return v
                        if isinstance(v, str):
                            return datetime.date.fromisoformat(v.split('T')[0])
                        return v

                    return to_date(row_val) < to_date(target_val)

                return row_val < target_val

            except (ValueError, TypeError, AttributeError):
                return False

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
                
        elif operator == 'not_subset_of':
            if row_val is None or target_val is None:
                return False

            def _as_field_set(v):
                # PostgreSQL JSONB may already arrive as a Python list.
                if isinstance(v, (list, tuple, set)):
                    return {str(x).strip() for x in v if str(x).strip()}

                # JSON string such as ["name", "email"]
                if isinstance(v, str):
                    try:
                        parsed = json.loads(v)
                        if isinstance(parsed, list):
                            return {
                                str(x).strip()
                                for x in parsed
                                if str(x).strip()
                            }
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # CSV-style string such as name,email,phone
                    return {
                        x.strip()
                        for x in v.split(',')
                        if x.strip()
                    }

                return {str(v).strip()}

            accessed_fields = _as_field_set(row_val)
            allowed_fields = _as_field_set(target_val)

            # Fires only when at least one accessed field
            # is outside the organisation's allowed set.
            return bool(accessed_fields - allowed_fields)

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
def evaluate_all_signals(rule_id, signals: list[dict], row: dict) -> tuple[dict[str, bool], list[str]]:
    """
    Evaluates all evidence signals for a given rule against a row dict.
    Returns:
        (results_dict, fields_triggered_list)
        where results_dict maps signal_id -> bool (fired),
        and fields_triggered_list contains all schema column names
        participating in any signal that evaluated to True.
    """
    results = {}
    fields_triggered = []

    for s in signals:
        signal_id = s.get('signal_id')
        if not signal_id:
            continue

        fired = evaluate_signal(rule_id, signal_id, s, row)
        results[signal_id] = fired

        if fired:
            # 1. Primary field involved in the signal condition
            field = s.get('field')
            if field:
                # Normalize legacy alias names to active schema names if needed
                if field == 'expiry_timestamp' and 'expiry_date' in row:
                    field = 'expiry_date'
                elif field == 'consent_timestamp' and 'consent_date' in row:
                    field = 'consent_date'
                elif field == 'timestamp' and 'event_date' in row:
                    field = 'event_date'
                elif field == 'timestamp' and 'access_date' in row:
                    field = 'access_date'
                elif field == 'submitted_at' and 'submitted_date' in row:
                    field = 'submitted_date'
                elif field == 'acknowledged_at' and 'acknowledged_date' in row:
                    field = 'acknowledged_date'
                elif field == 'fulfilled_at' and 'fulfilled_date' in row:
                    field = 'fulfilled_date'
                elif field == 'erasure_timestamp' and 'erasure_date' in row:
                    field = 'erasure_date'
                elif field == 'breach_confirmed_at' and 'breach_confirmed_date' in row:
                    field = 'breach_confirmed_date'

                fields_triggered.append(field)

            # 2. Target comparison value if it refers to a column in row
            val = s.get('value')
            if isinstance(val, str):
                if val == 'timestamp' and 'event_date' in row:
                    val = 'event_date'
                if val in row:
                    fields_triggered.append(val)

    # Return deduplicated, sorted list of fields triggered
    return results, sorted(list(set(fields_triggered)))


