"""
regulation_mapper.py
====================
Provides semantic similarity scoring between DPDP legal clauses
and the database tables that hold relevant evidence.

Uses sentence-transformers (all-MiniLM-L6-v2) to embed:
  - Clause texts: legal_text + plain_english_obligation (from clauses.json)
  - Table texts:  plain-English descriptions (from data/table_descriptions.json)

All embeddings are pre-computed at import time so individual lookup
calls are near-instant (pure cosine similarity, no model inference).

Public API:
  get_table_similarities(clause_id)       -> list[dict]  (all 10 tables, sorted)
  get_top_matching_tables(clause_id, ...) -> list[dict]  (above threshold)
  enrich_mapped_regulation(entry)         -> dict         (adds semantic_similarity key)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent          # capstone_f/
_TABLE_DESCRIPTIONS_PATH = _ROOT / "data" / "table_descriptions.json"
_CLAUSES_PATH            = _ROOT / "data" / "dpdp_kb" / "clauses.json"

# ── Module-level state (populated at import) ──────────────────────────────────

_MODEL           = None
_TABLE_NAMES:    list[str]  = []
_TABLE_TEXTS:    list[str]  = []
_TABLE_EMBEDDINGS            = None   # Tensor (10, 384)
_CLAUSES:        dict       = {}
_CLAUSE_EMBEDDINGS: dict    = {}      # {clause_id: Tensor (384,)}
_TABLE_DESCRIPTIONS: dict   = {}

try:
    from sentence_transformers import SentenceTransformer, util as _st_util

    # ── Load model ────────────────────────────────────────────────────────────
    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("[regulation_mapper] Model loaded: all-MiniLM-L6-v2")

    # ── Load table descriptions ───────────────────────────────────────────────
    _TABLE_DESCRIPTIONS = json.loads(_TABLE_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    _TABLE_NAMES        = list(_TABLE_DESCRIPTIONS.keys())
    _TABLE_TEXTS        = list(_TABLE_DESCRIPTIONS.values())

    # ── Load clauses ──────────────────────────────────────────────────────────
    _raw_clauses = json.loads(_CLAUSES_PATH.read_text(encoding="utf-8"))
    _CLAUSES     = {c["clause_id"]: c for c in _raw_clauses}

    # ── Pre-compute table embeddings (one batch call) ─────────────────────────
    _TABLE_EMBEDDINGS = _MODEL.encode(
        _TABLE_TEXTS,
        convert_to_tensor=True,
        show_progress_bar=False,
    )
    logger.info(
        "[regulation_mapper] Table embeddings computed for %d tables.", len(_TABLE_NAMES)
    )

    # ── Pre-compute clause embeddings (one per clause) ────────────────────────
    _clause_ids   = list(_CLAUSES.keys())
    _clause_texts = [
        f"{c['legal_text']} {c['plain_english_obligation']}"
        for c in _CLAUSES.values()
    ]
    _CLAUSE_EMBEDDINGS = {
        cid: _MODEL.encode(text, convert_to_tensor=True, show_progress_bar=False)
        for cid, text in zip(_clause_ids, _clause_texts)
    }
    logger.info(
        "[regulation_mapper] Clause embeddings computed for %d clauses.", len(_clause_ids)
    )

except ImportError:
    logger.warning(
        "[regulation_mapper] sentence-transformers not available. "
        "Semantic enrichment will be skipped."
    )
except Exception as _init_exc:
    logger.warning(
        "[regulation_mapper] Initialisation failed: %s. "
        "Semantic enrichment will be skipped.",
        _init_exc,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def get_table_similarities(clause_id: str) -> list[dict]:
    """
    Returns a sorted list of all 10 database tables with their cosine
    similarity scores against the given clause.

    Each dict has:
      {
        'table':            str,
        'similarity_score': float,   # cosine similarity, 4 decimal places
        'description':      str,
      }

    Returns an empty list if the model is unavailable or clause_id is unknown.
    """
    if _MODEL is None:
        return []

    if clause_id not in _CLAUSE_EMBEDDINGS:
        logger.warning("[regulation_mapper] Unknown clause_id: %s", clause_id)
        return []

    clause_embedding = _CLAUSE_EMBEDDINGS[clause_id]

    # cos_sim returns a (1, N) tensor; take row 0
    from sentence_transformers import util as _st_util
    similarities = _st_util.cos_sim(clause_embedding, _TABLE_EMBEDDINGS)[0]

    results = [
        {
            "table":            _TABLE_NAMES[i],
            "similarity_score": round(float(similarities[i]), 4),
            "description":      _TABLE_DESCRIPTIONS[_TABLE_NAMES[i]],
        }
        for i in range(len(_TABLE_NAMES))
    ]

    return sorted(results, key=lambda x: x["similarity_score"], reverse=True)


def get_top_matching_tables(
    clause_id: str,
    threshold: float = 0.30,
    top_n: int = 3,
) -> list[dict]:
    """
    Returns only the tables whose cosine similarity to the given clause
    is >= threshold, capped at top_n results.

    Useful for annotating which tables are semantically relevant to a
    given legal obligation.
    """
    all_similarities = get_table_similarities(clause_id)
    return [t for t in all_similarities if t["similarity_score"] >= threshold][:top_n]


def enrich_mapped_regulation(mapped_reg_entry: dict) -> dict:
    """
    Takes one entry from the existing mapped_regulations list (as built by
    ReportingAgent._build_mapped_regulations) and adds a
    'semantic_similarity' key with the following structure:

      {
        'primary_table_score':  float,      # score for the DB-assigned primary table
        'top_matching_tables':  list[dict], # semantically closest tables (threshold 0.30)
        'mapping_method':       str,
        'model_grounded':       bool,
      }

    If enrichment fails for any reason, the original entry is returned unchanged.
    """
    clause_id = mapped_reg_entry.get("rule_id")

    all_similarities = get_table_similarities(clause_id)
    top_tables       = get_top_matching_tables(clause_id)

    # Look up the similarity score for the existing primary table
    primary_table = (mapped_reg_entry.get("system_tables_involved") or [""])[0]
    primary_score = next(
        (t["similarity_score"] for t in all_similarities if t["table"] == primary_table),
        0.0,
    )

    mapped_reg_entry["semantic_similarity"] = {
        "primary_table_score":  primary_score,
        "top_matching_tables":  top_tables,
        "mapping_method":       "sentence-transformers/all-MiniLM-L6-v2",
        "model_grounded":       _MODEL is not None,
    }

    return mapped_reg_entry
