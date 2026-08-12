# src/config.py

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ── Root ────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent
DATA_DIR    = ROOT_DIR / "data"
SRC_DIR     = ROOT_DIR / "src"

# ── Data folders ────────────────────────────────────────
DPDP_KB_DIR  = DATA_DIR / "dpdp_kb"
LABELS_DIR   = DATA_DIR / "labels"
TENANTS_DIR  = DATA_DIR / "tenants"

# ── Output folders ───────────────────────────────────────
INDEXES_DIR  = ROOT_DIR / "indexes"
LOGS_DIR     = ROOT_DIR / "logs"
OUTPUTS_DIR  = ROOT_DIR / "outputs"
MODELS_DIR   = ROOT_DIR / "models"

# ── Key files ────────────────────────────────────────────
RULES_FILE        = DPDP_KB_DIR / "dpdp_rules.json"
CLAUSES_FILE      = DPDP_KB_DIR / "clauses.json"
GROUND_TRUTH_FILE = LABELS_DIR  / "ground_truth.json"
AUDIT_LOG_FILE    = LOGS_DIR    / "audit.log.jsonl"

# ── Tenant path helpers ──────────────────────────────────
def tenant_raw_dir(tenant_id: str) -> Path:
    return TENANTS_DIR / tenant_id / "raw"

def tenant_redacted_dir(tenant_id: str) -> Path:
    return TENANTS_DIR / tenant_id / "redacted"

def tenant_index_path(tenant_id: str) -> Path:
    return INDEXES_DIR / tenant_id / "faiss.index"

def tenant_index_meta_path(tenant_id: str) -> Path:
    return INDEXES_DIR / tenant_id / "metadata.json"

# ── Model settings ───────────────────────────────────────
EMBEDDING_MODEL  = "BAAI/bge-small-en-v1.5"
RISK_MODEL_PATH  = MODELS_DIR / "risk_model" / "risk_model.pkl"
MODEL_VERSION    = "xgb-v1-frozen"
TOP_K_RETRIEVAL  = 5

# ── API ──────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ENVIRONMENT    = os.getenv("ENVIRONMENT", "development")