"""
verify_auth.py — All 8 auth verification tests for Part 2 governance layer.
"""

import sys
import json
import requests

BASE = "http://127.0.0.1:8000"

def title(n, desc):
    print(f"\n{'='*60}")
    print(f"TEST {n}: {desc}")
    print('='*60)

def check(resp, expected_status, label):
    status_ok = resp.status_code == expected_status
    mark = "PASS" if status_ok else "FAIL"
    print(f"  [{mark}] Status: {resp.status_code} (expected {expected_status})")
    try:
        body = resp.json()
        print(f"  Body: {json.dumps(body, indent=2)[:300]}")
    except Exception:
        print(f"  Body (raw): {resp.text[:200]}")
    return status_ok

results = {}

# ── TEST 1: GET /health — no token needed ─────────────────────────────────────
title(1, "GET /health — no auth required (expect 200)")
r = requests.get(f"{BASE}/health")
results[1] = check(r, 200, "health open")

# ── TEST 2: POST /analyze — no token (expect 401) ─────────────────────────────
title(2, "POST /analyze — no token (expect 401)")
r = requests.post(f"{BASE}/analyze", json={"tenant_id": "tenant_a"})
results[2] = check(r, 401, "analyze no token")

# ── TEST 3: POST /auth/token — viewer login (expect 200 + token) ──────────────
title(3, "POST /auth/token — viewer login (expect 200)")
r = requests.post(
    f"{BASE}/auth/token",
    data={"username": "viewer", "password": "viewer123"},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
results[3] = check(r, 200, "viewer login")
viewer_token = None
if r.status_code == 200:
    viewer_token = r.json().get("access_token")
    print(f"  Token (first 40 chars): {viewer_token[:40]}...")

# ── Also get reviewer & admin tokens for later tests ─────────────────────────
r2 = requests.post(
    f"{BASE}/auth/token",
    data={"username": "reviewer", "password": "reviewer123"},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
reviewer_token = r2.json().get("access_token") if r2.status_code == 200 else None

r3 = requests.post(
    f"{BASE}/auth/token",
    data={"username": "admin", "password": "admin123"},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
admin_token = r3.json().get("access_token") if r3.status_code == 200 else None

# ── TEST 4: GET /rules — viewer token (expect 200) ───────────────────────────
# (Using /rules instead of /analyze/upload to avoid needing 10 CSV files)
title(4, "GET /rules — viewer token (expect 200)")
headers_viewer = {"Authorization": f"Bearer {viewer_token}"} if viewer_token else {}
r = requests.get(f"{BASE}/rules", headers=headers_viewer)
results[4] = check(r, 200, "rules with viewer token")

# ── TEST 5: GET /rules/proposed — viewer token (expect 403) ──────────────────
title(5, "GET /rules/proposed — viewer token (expect 403)")
r = requests.get(f"{BASE}/rules/proposed", headers=headers_viewer)
results[5] = check(r, 403, "proposed rules viewer blocked")

# ── TEST 6: GET /rules/proposed — reviewer token (expect 200) ────────────────
title(6, "GET /rules/proposed — reviewer token (expect 200)")
headers_reviewer = {"Authorization": f"Bearer {reviewer_token}"} if reviewer_token else {}
r = requests.get(f"{BASE}/rules/proposed", headers=headers_reviewer)
results[6] = check(r, 200, "proposed rules reviewer allowed")

# ── TEST 7: POST /rules/approve/999 — reviewer token (expect 403) ────────────
title(7, "POST /rules/approve/999 — reviewer token (expect 403)")
r = requests.post(f"{BASE}/rules/approve/999", headers=headers_reviewer)
results[7] = check(r, 403, "approve reviewer blocked")

# ── TEST 8: POST /rules/approve/999 — admin token (expect 200 or 404) ─────────
title(8, "POST /rules/approve/999 — admin token (expect 200 or 404, NOT 403)")
headers_admin = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
r = requests.post(f"{BASE}/rules/approve/999", headers=headers_admin)
# 404 = admin has access but proposal doesn't exist — that's correct
results[8] = r.status_code in (200, 404)
mark = "PASS" if results[8] else "FAIL"
print(f"  [{mark}] Status: {r.status_code} (expected 200 or 404, NOT 403)")
try:
    print(f"  Body: {json.dumps(r.json(), indent=2)[:300]}")
except Exception:
    print(f"  Body (raw): {r.text[:200]}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("SUMMARY")
print('='*60)
passed = sum(1 for v in results.values() if v)
for n, ok in sorted(results.items()):
    print(f"  Test {n}: {'PASS' if ok else 'FAIL'}")
print(f"\n  {passed}/{len(results)} tests passed")

sys.exit(0 if passed == len(results) else 1)
