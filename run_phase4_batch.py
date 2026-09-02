"""
run_phase4_batch.py
====================
Driver for Phase 4 data generation: runs profiles from generator_config.json
through the real pipeline (generate -> anonymize -> compliance analysis ->
evaluation_results), using the fixed generate_data.process_profile().

Usage:
    python run_phase4_batch.py --sanity      # first 8 profiles, spread across families
    python run_phase4_batch.py --full        # all 315 profiles
"""
import sys
import json
import random
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.generate_data import process_profile

CONFIG_PATH = Path("data/generator_config.json")
REPORT_PATH = Path("phase4_generation_report.json")


def pick_sanity_profiles(profiles):
    # One from each of the 5 severity families, plus a few unique named personas.
    families = ["compliant_fintech", "low_risk_fintech", "medium_risk_fintech",
                "high_risk_fintech", "critical_risk_fintech"]
    chosen = []
    for fam in families:
        for p in profiles:
            if p["profile_name"].startswith(fam):
                chosen.append(p)
                break
    named = [p for p in profiles if not any(p["profile_name"].startswith(f) for f in families)]
    chosen.extend(named[:3])
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sanity", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    if args.sanity:
        profiles = pick_sanity_profiles(profiles)
        print(f"SANITY MODE: running {len(profiles)} profiles: {[p['profile_name'] for p in profiles]}")
    elif args.full:
        print(f"FULL MODE: running all {len(profiles)} profiles")
    else:
        print("Pass --sanity or --full")
        sys.exit(1)

    random.seed(42)
    reports = []
    for idx, profile in enumerate(profiles, 1):
        tenant_id = profile["tenant_id"]
        print(f"\n[{idx}/{len(profiles)}] {tenant_id} ({profile['profile_name']})")
        try:
            report = process_profile(profile)
        except Exception as e:
            import traceback
            traceback.print_exc()
            report = {"tenant_id": tenant_id, "profile_name": profile["profile_name"],
                       "status": "fatal_error", "error": str(e)}
        reports.append(report)

    success = sum(1 for r in reports if str(r.get("status", "")).startswith("success"))
    print(f"\n{'='*60}\n{success}/{len(reports)} succeeded\n{'='*60}")
    for r in reports:
        if not str(r.get("status", "")).startswith("success"):
            print(f"  FAILED: {r['tenant_id']} ({r.get('profile_name')}) -- {r.get('error')}")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, default=str)
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
