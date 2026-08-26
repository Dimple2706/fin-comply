# tests/test_data.py

import json
from pathlib import Path

def load_json(path):
    with open(path) as f:
        return json.load(f)

def flatten(data):
    """Pull all fields from nested JSON into one flat dict."""
    fields = {}
    if isinstance(data, dict):
        for k, v in data.items():
            fields[k] = v
            if isinstance(v, (dict, list)):
                fields.update(flatten(v))
    elif isinstance(data, list):
        for item in data:
            fields.update(flatten(item))
    return fields

def test_tenant_data_field_coverage():
    # ── Load rules ───────────────────────────────────────
    rules = load_json("data/dpdp_kb/dpdp_rules.json")
    print(f"\n✓ Loaded {len(rules)} rules from dpdp_rules.json")

    # ── Collect all signal IDs rules expect ─────────────
    expected_fields = set()
    for rule in rules:
        signals = rule.get("evidence_signals", [])
        for sig in signals:
            expected_fields.add(sig.get("signal_id"))

    print(f"✓ Rules expect these fields: {sorted(expected_fields)}")

    # ── Test each tenant ─────────────────────────────────
    for tenant in ["tenant_a", "tenant_b"]:
        print(f"\n── Checking {tenant} ──")

        redacted_dir = Path(f"data/tenants/{tenant}/redacted")
        if not redacted_dir.exists():
            continue
        files = list(redacted_dir.glob("*.json"))

        if not files:
            print(f"  ✗ No files found in {redacted_dir}")
            continue

        # Flatten all files into one dict
        all_fields = {}
        for f in files:
            data = load_json(f)
            all_fields.update(flatten(data))
            print(f"  ✓ Loaded {f.name}")

        # Check which expected fields are present
        print(f"\n  Field coverage:")
        missing = []
        for field in sorted(expected_fields):
            if field in all_fields:
                print(f"    ✓  {field}: {all_fields[field]}")
            else:
                print(f"    ✗  {field}: MISSING")
                missing.append(field)