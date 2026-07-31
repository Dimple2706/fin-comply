import json
import sys
import os

# Add root dir to sys.path so we can import data.generate_data
sys.path.append(os.path.abspath('.'))

from data.generate_data import process_profile

def generate_new_profiles():
    with open("data/generator_config.json", "r") as f:
        configs = json.load(f)
        
    for p in configs:
        if p["tenant_id"] >= "GEN-251":
            print(f"Generating data for {p['tenant_id']}...")
            process_profile(p)

if __name__ == "__main__":
    generate_new_profiles()
