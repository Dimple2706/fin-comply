import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_ood_testset as g

N = 45
START = 22150
profiles = []
tid = START
for _ in range(N):
    profiles.append(g.build_profile(g.all_off_vector(), f"GEN-{tid}", "compliant_topup"))
    tid += 1

print(f"Generating {len(profiles)} COMPLIANT top-up tenants, starting GEN-{START}")
g.run_batch(profiles, "ood_v2_compliant_topup_report.json")
