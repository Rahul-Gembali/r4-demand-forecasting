"""Live integration verification script for FastAPI endpoints."""

import requests
import json

BASE = "http://127.0.0.1:8000"
ADMIN_HEADERS = {"X-API-Key": "r4-admin-key-2026"}
OPERATOR_HEADERS = {"X-API-Key": "r4-operator-key-2026"}
VIEWER_HEADERS = {"X-API-Key": "r4-viewer-key-2026"}

def run_checks():
    print("=== 1. Health Probe ===")
    r = requests.get(f"{BASE}/health")
    print(f"GET /health -> HTTP {r.status_code}")
    print(" ", r.json())
    assert r.status_code == 200

    print("\n=== 2. Readiness Probe ===")
    r = requests.get(f"{BASE}/ready")
    print(f"GET /ready -> HTTP {r.status_code}")
    print(" ", r.json())
    assert r.status_code == 200

    print("\n=== 3. Unauthorized Test ===")
    r = requests.get(f"{BASE}/api/v1/models")
    print(f"GET /api/v1/models (No Auth) -> HTTP {r.status_code}")
    print(" ", r.json())
    assert r.status_code == 401

    print("\n=== 4. List Models (Viewer) ===")
    r = requests.get(f"{BASE}/api/v1/models", headers=VIEWER_HEADERS)
    print(f"GET /api/v1/models (Viewer) -> HTTP {r.status_code}")
    data = r.json()
    print(f"  Count: {len(data['models'])}")
    if data['models']:
        m = data['models'][0]
        print(f"  First Model: {m['model_id']} | Algorithm: {m['algorithm']} | Val WAPE: {m['validation_wape']}")
    assert r.status_code == 200

    print("\n=== 5. Forecast Run Summary ===")
    r = requests.get(f"{BASE}/api/v1/forecasts/RUN_EVAL_150_V1", headers=VIEWER_HEADERS)
    print(f"GET /api/v1/forecasts/RUN_EVAL_150_V1 -> HTTP {r.status_code}")
    d = r.json()
    print(f"  Status: {d.get('status')} | SKUs: {d.get('sku_count')}")
    print(f"  Total Recommended Buy Units: {d.get('total_recommended_buy_units'):,}")
    print(f"  Average Confidence Score: {d.get('average_confidence_score'):.1f}/100")
    print(f"  Expected Financial Investment: ${d.get('total_expected_cost'):,.2f}")
    assert r.status_code == 200

    print("\n=== 6. Single SKU Forecast Detail (SKU_EVAL_001) ===")
    r = requests.get(f"{BASE}/api/v1/forecasts/RUN_EVAL_150_V1/skus/SKU_EVAL_001", headers=VIEWER_HEADERS)
    print(f"GET .../skus/SKU_EVAL_001 -> HTTP {r.status_code}")
    d = r.json()
    print(f"  Name: {d.get('product_name')} | Cat: {d.get('category')} | Price: ${d.get('base_price')}")
    print(f"  Weekly Forecasts: {len(d.get('forecasts', []))} weeks | First Week: {d['forecasts'][0]['predicted_sales']} units (80% CI: [{d['forecasts'][0]['lower_bound_80']}, {d['forecasts'][0]['upper_bound_80']}])")
    if d.get("recommendation"):
        rec = d["recommendation"]
        print(f"  Recommended Buy Qty: {rec['recommended_buy_quantity']} units | Critical Ratio: {rec['critical_ratio']}")
    if d.get("analogues"):
        an = d["analogues"][0]
        print(f"  Top Analogue: {an['analogue_sku_id']} | Similarity: {an['similarity_score']:.4f}")
    assert r.status_code == 200

    print("\n=== 7. Low-Confidence SKUs ===")
    r = requests.get(f"{BASE}/api/v1/forecasts/RUN_EVAL_150_V1/low-confidence?limit=3", headers=VIEWER_HEADERS)
    print(f"GET .../low-confidence?limit=3 -> HTTP {r.status_code}")
    d = r.json()
    for idx, itm in enumerate(d.get('items', []), 1):
        print(f"  [{idx}] {itm['sku_id']} | Conf: {itm['confidence_score']:.1f} ({itm['confidence_tier']}) | Rec Buy: {itm['recommended_buy_quantity']}")
    assert r.status_code == 200

    print("\n=== 8. Inventory Optimization Scenario ===")
    payload = {
        "run_id": "RUN_EVAL_150_V1",
        "scenario_name": "CONSERVATIVE_API",
        "understock_cost_cu": 20.0,
        "overstock_cost_co": 40.0,
        "min_order_quantity": 50,
        "case_pack_size": 12,
    }
    r = requests.post(f"{BASE}/api/v1/inventory/optimize", headers=OPERATOR_HEADERS, json=payload)
    print(f"POST /api/v1/inventory/optimize -> HTTP {r.status_code}")
    d = r.json()
    print(f"  Optimized SKUs: {d.get('total_skus_optimized')} | Total Units: {d.get('total_buy_units'):,} | Fill Rate: {d.get('average_fill_rate_pct')}%")
    assert r.status_code == 200

    print("\n=== 9. Executive Evaluation Report ===")
    r = requests.get(f"{BASE}/api/v1/reports/RUN_EVAL_150_V1", headers=VIEWER_HEADERS)
    print(f"GET /api/v1/reports/RUN_EVAL_150_V1 -> HTTP {r.status_code}")
    d = r.json()
    print(f"  WAPE: {d.get('portfolio_metrics', {}).get('overall_wape')} | Empirical Coverage 90%: {d.get('uncertainty_calibration', {}).get('empirical_coverage_90')}")
    print(f"  Recorded Data Manifests: {len(d.get('data_manifests', []))}")
    assert r.status_code == 200

    print("\n=== 10. Validation Error (422) Test ===")
    r = requests.post(f"{BASE}/api/v1/models/train", headers=ADMIN_HEADERS, json={"iterations": -5})
    print(f"POST /api/v1/models/train (Invalid) -> HTTP {r.status_code} | Code: {r.json()['error']['code']}")
    assert r.status_code == 422

    print("\n=== 11. Missing Run (404) Test ===")
    r = requests.get(f"{BASE}/api/v1/forecasts/RUN_MISSING_123", headers=VIEWER_HEADERS)
    print(f"GET /api/v1/forecasts/RUN_MISSING_123 -> HTTP {r.status_code} | Code: {r.json()['error']['code']}")
    assert r.status_code == 404

    print("\n=== ALL 11 LIVE API CHECKS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_checks()
