#!/usr/bin/env python3
"""
Test the API upload endpoint to verify all violations are detected
"""

import json
import requests
from pathlib import Path

import pytest

BASE_URL = "http://localhost:8000"
UPLOAD_ENDPOINT = f"{BASE_URL}/analyze/upload"

@pytest.mark.skip(reason="Manual only local integration script requiring running API server and specific local path")
def test_api_upload():
    """Test /analyze/upload endpoint with tenant_c data"""
    print("\n" + "="*80)
    print("🧪 TESTING API /analyze/upload ENDPOINT")
    print("="*80)
    
    files_path = Path(r"C:\Users\Shravani Bhosale\Downloads")
    
    files = {
        'policies': open(files_path / "tenant_c_policies (1).json", 'rb'),
        'logs': open(files_path / "tenant_c_logs.json", 'rb'),
        'inventory': open(files_path / "tenant_c_sysinven.json", 'rb'),
    }
    
    print("\n📤 Uploading tenant_c files to API...")
    print(f"   - policies.json")
    print(f"   - logs.json (50 entries)")
    print(f"   - system_inventory.json")
    
    try:
        response = requests.post(UPLOAD_ENDPOINT, files=files)
        
        if response.status_code == 200:
            data = response.json()
            
            print("\n✅ API Response Received:")
            print(f"   Tenant ID: {data['tenant_id']}")
            print(f"   Status: {data['status']}")
            print(f"   Violation Count: {data['violation_count']}")
            print(f"   Risk Score: {data['risk_score']}")
            print(f"   Risk Tier: {data['risk_tier']}")
            
            print("\n📊 Violations Detected:")
            if data['violations']:
                violations_by_rule = {}
                for v in data['violations']:
                    rule_id = v['rule_id']
                    if rule_id not in violations_by_rule:
                        violations_by_rule[rule_id] = []
                    violations_by_rule[rule_id].append(v)
                
                for rule_id in sorted(violations_by_rule.keys()):
                    count = len(violations_by_rule[rule_id])
                    rule_name = violations_by_rule[rule_id][0]['rule_name']
                    print(f"   {rule_id}: {count} violation(s) - {rule_name}")
            
            total = data['violation_count']
            print(f"\n   📈 TOTAL: {total} violations")
            
            if total > 5:
                print(f"\n   ✅ SUCCESS! Now detecting {total} violations (was 5 before)")
            else:
                print(f"\n   ⚠️  Still showing only {total} violations - API might not be using the endpoint")
        else:
            print(f"\n❌ API Error: {response.status_code}")
            print(response.text)
    
    except requests.exceptions.ConnectionError:
        print("\n⚠️  ERROR: Cannot connect to API at http://localhost:8000")
        print("   Make sure uvicorn is running:")
        print("   uvicorn src.api.main:app --reload --port 8000")
    
    finally:
        for f in files.values():
            f.close()

if __name__ == "__main__":
    test_api_upload()
    print("\n" + "="*80 + "\n")
