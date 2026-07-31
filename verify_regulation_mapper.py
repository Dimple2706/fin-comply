"""
Task 4 verification — ASCII-safe output for Windows cp1252 console.
"""
import json
import time
import sys
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PASS = "PASS"
FAIL = "FAIL"

def check(label, condition):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")

print("=" * 60)
print("TASK 0 - Import check")
print("=" * 60)
try:
    from sentence_transformers import SentenceTransformer
    print("sentence-transformers import: OK")
except ImportError as e:
    print(f"sentence-transformers import: FAILED - {e}")
    raise SystemExit(1)

# Phase 1 - mapper standalone
print("\n" + "=" * 60)
print("PHASE 1 - regulation_mapper standalone checks")
print("=" * 60)

t0 = time.time()
from src.intelligence.regulation_mapper import (
    get_table_similarities,
    get_top_matching_tables,
    enrich_mapped_regulation,
    _MODEL,
)
import_time = round(time.time() - t0, 2)
print(f"Import + pre-compute time (model cached): {import_time}s")
print(f"model_grounded: {_MODEL is not None}")

# Q2 - DPDP-001
print("\n--- Q2: DPDP-001 (Consent for Processing) top_matching_tables ---")
tops_001 = get_top_matching_tables('DPDP-001')
for t in tops_001:
    print(f"  {t['table']:30s}  score={t['similarity_score']}")
top_001 = tops_001[0]['table'] if tops_001 else 'none'
check(f"DPDP-001 top table == consent_records (got: {top_001})", top_001 == 'consent_records')
consent_score = next((t['similarity_score'] for t in tops_001 if t['table'] == 'consent_records'), 0.0)
print(f"  consent_records similarity score: {consent_score}")

# Q3 - DPDP-013
print("\n--- Q3: DPDP-013 (Unauthorised Employee Access) top_matching_tables ---")
tops_013 = get_top_matching_tables('DPDP-013', threshold=0.0, top_n=3)
for t in tops_013:
    print(f"  {t['table']:30s}  score={t['similarity_score']}")
top_013 = tops_013[0]['table'] if tops_013 else 'none'
check(f"DPDP-013 top table == access_logs (got: {top_013})", top_013 == 'access_logs')

# DPDP-003 check
print("\n--- DPDP-003 (Storage Limitation) -> data_lifecycle ---")
all_003 = get_table_similarities('DPDP-003')
top_003 = all_003[0]['table'] if all_003 else 'none'
dl_score = next((t['similarity_score'] for t in all_003 if t['table'] == 'data_lifecycle'), 0.0)
for t in all_003[:3]:
    print(f"  {t['table']:30s}  score={t['similarity_score']}")
check(f"DPDP-003 top table == data_lifecycle (got: {top_003})", top_003 == 'data_lifecycle')
print(f"  data_lifecycle score: {dl_score}")

# DPDP-014 check
print("\n--- DPDP-014 (Breach Notification) -> security_events ---")
all_014 = get_table_similarities('DPDP-014')
top_014 = all_014[0]['table'] if all_014 else 'none'
sec_score = next((t['similarity_score'] for t in all_014 if t['table'] == 'security_events'), 0.0)
for t in all_014[:3]:
    print(f"  {t['table']:30s}  score={t['similarity_score']}")
check(f"DPDP-014 top table == security_events (got: {top_014})", top_014 == 'security_events')
print(f"  security_events score: {sec_score}")

# Q4 - Timing
print("\n--- Q4: Subsequent call timing (embeddings cached in memory) ---")
t1 = time.time(); _ = get_table_similarities('DPDP-001'); t2 = time.time()
t3 = time.time(); _ = get_table_similarities('DPDP-014'); t4 = time.time()
t5 = time.time(); _ = get_table_similarities('DPDP-013'); t6 = time.time()
print(f"  DPDP-001: {round((t2-t1)*1000, 2)}ms")
print(f"  DPDP-014: {round((t4-t3)*1000, 2)}ms")
print(f"  DPDP-013: {round((t6-t5)*1000, 2)}ms")

# enrich test
print("\n--- enrich_mapped_regulation() standalone (DPDP-003) ---")
mock_entry = {
    "rule_id": "DPDP-003",
    "dpdp_section": "Section 8(7)",
    "legal_title": "Storage Limitation",
    "plain_english_obligation": "Data must not be kept longer than necessary.",
    "system_tables_involved": ["data_lifecycle"],
    "agent_responsible": "audit_agent",
    "violation_status": "VIOLATION",
}
enriched = enrich_mapped_regulation(mock_entry)
sem = enriched.get('semantic_similarity', {})
print(f"  primary_table_score (data_lifecycle): {sem.get('primary_table_score')}")
print(f"  mapping_method: {sem.get('mapping_method')}")
print(f"  model_grounded: {sem.get('model_grounded')}")
check("model_grounded == True", sem.get('model_grounded') == True)

# Full 16-clause table
print("\n--- All 16 clauses top matching table ---")
with open('data/dpdp_kb/clauses.json', encoding='utf-8') as f:
    all_clauses = json.load(f)
for c in all_clauses:
    cid = c['clause_id']
    tops = get_top_matching_tables(cid, threshold=0.0, top_n=1)
    top_table = tops[0]['table'] if tops else 'none'
    top_score = tops[0]['similarity_score'] if tops else 0.0
    print(f"  {cid:12s} {c['legal_title'][:42]:42s} -> {top_table} ({top_score})")

# Phase 2 - orchestrator
print("\n" + "=" * 60)
print("PHASE 2 - Full orchestrator integration (requires DB)")
print("=" * 60)
try:
    from src.agent_layer.orchestrator import run_compliance_analysis
    t_start = time.time()
    report = run_compliance_analysis('tenant_a')
    t_end = time.time()
    print(f"run_compliance_analysis completed in {round(t_end - t_start, 2)}s")
    mapped = report.get('mapped_regulations', [])
    print(f"Total mapped_regulations entries: {len(mapped)}")
    enriched_count = sum(1 for e in mapped if 'semantic_similarity' in e)
    all_grounded = all(
        e.get('semantic_similarity', {}).get('model_grounded', False)
        for e in mapped if 'semantic_similarity' in e
    )
    check(f"All {len(mapped)} entries enriched ({enriched_count} have semantic_similarity)", enriched_count == len(mapped))
    check("All model_grounded == True", all_grounded)
    print("\n--- First entry semantic_similarity block ---")
    if mapped and 'semantic_similarity' in mapped[0]:
        print(json.dumps(mapped[0]['semantic_similarity'], indent=2))
    dpdp003 = next((e for e in mapped if e['rule_id'] == 'DPDP-003'), None)
    if dpdp003:
        s = dpdp003.get('semantic_similarity', {})
        print(f"\nDPDP-003 primary_table_score: {s.get('primary_table_score')}")
    dpdp014 = next((e for e in mapped if e['rule_id'] == 'DPDP-014'), None)
    if dpdp014:
        s = dpdp014.get('semantic_similarity', {})
        top = (s.get('top_matching_tables') or [{}])[0].get('table', '?')
        print(f"DPDP-014 top_matching_table: {top}")
        check(f"DPDP-014 top == security_events (got: {top})", top == 'security_events')
except Exception as e:
    print(f"PHASE 2 FAILED - {e}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
