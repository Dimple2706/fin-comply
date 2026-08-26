import json
from src.agent_layer.orchestrator import run_compliance_analysis

def run_tenant_test(tenant_id):
    print(f"=== Testing {tenant_id} ===")
    report = run_compliance_analysis(tenant_id)
    ml_layer = report.get('ml_layer', {})
    
    ml_available = ml_layer.get('ml_available')
    print(f"ml_available == True: {ml_available == True}")
    
    predicted_tier = ml_layer.get('predicted_tier')
    print(f"predicted_tier is valid: {predicted_tier in ['COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']}")
    
    probs = ml_layer.get('probabilities', {})
    sum_probs = sum(probs.values())
    print(f"probabilities sum to 100%: {round(sum_probs, 1)}% == 100.0%")
    
    shap_exp = ml_layer.get('shap_explanation', {})
    # It might be the full mock dict or the 13 key dict
    if "feature_contributions" in shap_exp:
        print(f"shap_explanation has 13 keys (in feature_contributions): {len(shap_exp['feature_contributions']) == 13}")
    else:
        print(f"shap_explanation has 13 keys: {len(shap_exp) == 13}")
        
    lime_exp = ml_layer.get('lime_explanation', {})
    top_features = lime_exp.get('top_features', [])
    print(f"lime_explanation.top_features has at least 3 entries: {len(top_features) >= 3}")
    
    agrees = ml_layer.get('agrees_with_deterministic')
    print(f"agrees_with_deterministic exists: {agrees is not None} (Value: {agrees})")
    
    if tenant_id == 'GEN-010':
        print("\n--- Full ML Layer Output for GEN-010 ---")
        print(json.dumps(ml_layer, indent=2))
        
if __name__ == "__main__":
    run_tenant_test('tenant_a')
    print("\n")
    run_tenant_test('GEN-010')
