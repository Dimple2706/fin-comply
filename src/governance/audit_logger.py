import json
import logging
import datetime
import threading
import sys
from typing import Optional, Dict, Any

from src.config import AUDIT_LOG_FILE, LOGS_DIR

ANALYSIS_RUN = "analysis_run"
LLM_CALL = "llm_call"
LLM_BLOCKED = "llm_pii_blocked"
RULE_APPROVED = "rule_approved"
RULE_REJECTED = "rule_rejected"
RULE_PROPOSED = "rule_proposed"
MODEL_LOADED = "model_loaded"
MODEL_LOAD_FAILED = "model_load_failed"
APP_STARTUP = "app_startup"

_audit_lock = threading.Lock()

def _ensure_log_file():
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if not AUDIT_LOG_FILE.exists():
            AUDIT_LOG_FILE.touch()
    except Exception as e:
        print(f"Warning: Failed to ensure audit log file exists: {e}", file=sys.stderr)

_ensure_log_file()

def log_event(event_type: str, details: Dict[str, Any], user: Optional[str] = None, tenant_id: Optional[str] = None):
    try:
        event = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "user": user if user is not None else "system",
            "tenant_id": tenant_id,
            "details": details
        }
        
        with _audit_lock:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
    except Exception as e:
        print(f"Warning: Failed to write to audit log: {e}", file=sys.stderr)
