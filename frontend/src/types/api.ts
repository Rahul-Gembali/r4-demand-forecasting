/**
 * Typed API interfaces for R4 Demand Forecasting Dashboard.
 * Matches backend Pydantic schemas exactly.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
}

export interface ReadinessResponse {
  ready: boolean;
  components: {
    database: { status: string; details: string };
    model_registry: { status: string; details: string };
    storage: { status: string; details: string };
  };
  timestamp: string;
}

export interface ModelVersionItem {
  model_id: string;
  algorithm: string;
  objective: string;
  target_transform: string;
  artifact_path: string;
  validation_wape: number | null;
  hyperparameters?: Record<string, any>;
  feature_schema?: Record<string, any>;
  created_at: string;
}

export interface ForecastRunResponse {
  run_id: string;
  model_id: string;
  status: string;
  sku_count: number;
  created_at: string;
  completed_at: string | null;
  overall_wape: number | null;
  overall_bias_pct: number | null;
  total_recommended_buy_units: number;
  total_expected_cost: number;
  average_confidence_score: number;
  average_fill_rate_pct: number;
}

export interface WeeklyForecastItem {
  horizon_week: number;
  predicted_sales: number;
  lower_bound_80: number | null;
  upper_bound_80: number | null;
  lower_bound_90: number | null;
  upper_bound_90: number | null;
}

export interface AnalogueMatchDetail {
  rank: number;
  analogue_sku_id: string;
  similarity_score: number;
  observed_curve: number[] | null;
}

export interface InventoryRecDetail {
  scenario: string;
  forecast_cumulative_8w: number;
  recommended_buy_quantity: number;
  critical_ratio: number;
  understock_cost_cu: number;
  overstock_cost_co: number;
  expected_shortage_units: number;
  expected_excess_units: number;
  expected_total_cost: number;
  expected_fill_rate_pct: number;
  confidence_score: number | null;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW" | null;
  explanation_summary: string | null;
  assumptions?: Record<string, any>;
}

export interface SKUForecastDetail {
  sku_id: string;
  product_name: string;
  category: string;
  subcategory: string;
  colour?: string;
  material?: string;
  base_price: number;
  brand?: string;
  brand_tier?: string;
  launch_date: string;
  has_marketing_support: boolean;
  is_evaluation_sku: boolean;
  forecasts: WeeklyForecastItem[];
  recommendation: InventoryRecDetail | null;
  analogues: AnalogueMatchDetail[];
}

export interface SKUForecastListItem {
  sku_id: string;
  product_name: string;
  category: string;
  subcategory: string;
  colour?: string;
  material?: string;
  base_price: number;
  brand_tier?: string;
  launch_date: string;
  has_marketing_support: boolean;
  is_evaluation_sku: boolean;
  total_projected_sales: number;
  recommended_buy_quantity: number;
  confidence_score: number | null;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW";
  expected_total_cost?: number;
  expected_fill_rate_pct?: number;
  weekly_forecasts: number[];
}

export interface SKUForecastListResponse {
  run_id: string;
  total: number;
  items: SKUForecastListItem[];
}

export interface LowConfidenceSKUItem {
  sku_id: string;
  product_name: string;
  category: string;
  subcategory: string;
  base_price: number;
  confidence_score: number;
  confidence_tier: "HIGH" | "MEDIUM" | "LOW";
  forecast_cumulative_8w: number;
  recommended_buy_quantity: number;
  explanation_summary?: string;
  assumptions?: Record<string, any>;
}

export interface LowConfidenceResponse {
  run_id: string;
  count: number;
  items: LowConfidenceSKUItem[];
}

export interface InventoryOptimizeRequest {
  run_id: string;
  scenario_name: string;
  understock_cost_cu?: number;
  overstock_cost_co?: number;
  min_order_quantity: number;
  case_pack_size: number;
}

export interface InventoryOptimizeResponse {
  run_id: string;
  scenario_name: string;
  total_skus_optimized: number;
  total_buy_units: number;
  total_expected_cost: number;
  average_fill_rate_pct: number;
  recommendations: Array<{
    sku_id: string;
    scenario: string;
    recommended_buy_quantity: number;
    critical_ratio: number;
    expected_total_cost: number;
    expected_fill_rate_pct: number;
  }>;
}

export interface ReportSummaryResponse {
  run_id: string;
  model_id: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  portfolio_metrics: {
    sku_count: number;
    overall_wape: number;
    overall_bias_pct: number;
    reproducibility_seed: number;
  };
  uncertainty_calibration: {
    conformal_method: string;
    target_coverage_80: number;
    empirical_coverage_80: number;
    target_coverage_90: number;
    empirical_coverage_90: number;
    cumulative_interval_efficiency: string;
    [key: string]: any;
  };
  inventory_summary: {
    total_recommended_buy_units: number;
    total_expected_cost: number;
    average_confidence_score: number;
    average_fill_rate_pct: number;
  };
  least_confident_skus_summary: Array<{
    sku_id: string;
    product_name: string;
    category: string;
    confidence_score: number;
    confidence_tier: string;
    recommended_buy_quantity: number;
  }>;
  data_manifests: Array<{
    manifest_type: string;
    file_identifier: string;
    sha256_checksum: string;
    row_count: number;
  }>;
}
