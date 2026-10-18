/**
 * Typed API Client for R4 Demand Forecasting Backend.
 */

import {
  ForecastRunResponse,
  HealthResponse,
  InventoryOptimizeRequest,
  InventoryOptimizeResponse,
  LowConfidenceResponse,
  ModelVersionItem,
  ReadinessResponse,
  ReportSummaryResponse,
  SKUForecastDetail,
  SKUForecastListResponse,
} from "../types/api";

const API_BASE = "/api/v1";
const DEFAULT_HEADERS: HeadersInit = {
  "Content-Type": "application/json",
  "X-API-Key": "r4-viewer-key-2026",
};

const OPERATOR_HEADERS: HeadersInit = {
  "Content-Type": "application/json",
  "X-API-Key": "r4-operator-key-2026",
};

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMsg = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson?.error?.message) {
        errorMsg = errJson.error.message;
      } else if (errJson?.detail) {
        errorMsg = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(errorMsg);
  }
  return res.json();
}

export const apiClient = {
  /** Liveness Probe */
  async checkHealth(): Promise<HealthResponse> {
    const res = await fetch("/health");
    return handleResponse<HealthResponse>(res);
  },

  /** Readiness Probe */
  async checkReadiness(): Promise<ReadinessResponse> {
    const res = await fetch("/ready");
    return handleResponse<ReadinessResponse>(res);
  },

  /** Registered Model Versions */
  async getModels(): Promise<ModelVersionItem[]> {
    const res = await fetch(`${API_BASE}/models`, { headers: DEFAULT_HEADERS });
    const data = await handleResponse<{ models: ModelVersionItem[]; total: number }>(res);
    return data.models;
  },

  /** Forecast Run Summary */
  async getForecastRun(runId: string = "RUN_EVAL_150_V1"): Promise<ForecastRunResponse> {
    const res = await fetch(`${API_BASE}/forecasts/${runId}`, { headers: DEFAULT_HEADERS });
    return handleResponse<ForecastRunResponse>(res);
  },

  /** List SKU Forecast Summaries */
  async listSKUForecasts(
    runId: string = "RUN_EVAL_150_V1",
    category?: string,
    search?: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<SKUForecastListResponse> {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (category && category !== "ALL") params.append("category", category);
    if (search && search.trim()) params.append("search", search.trim());
    const res = await fetch(`${API_BASE}/forecasts/${runId}/skus?${params.toString()}`, {
      headers: DEFAULT_HEADERS,
    });
    return handleResponse<SKUForecastListResponse>(res);
  },

  /** Single SKU Forecast Detail */
  async getSKUForecast(runId: string, skuId: string): Promise<SKUForecastDetail> {
    const res = await fetch(`${API_BASE}/forecasts/${runId}/skus/${skuId}`, { headers: DEFAULT_HEADERS });
    return handleResponse<SKUForecastDetail>(res);
  },

  /** Least-Confident SKUs Ranking */
  async getLowConfidenceSKUs(runId: string = "RUN_EVAL_150_V1", limit: number = 10): Promise<LowConfidenceResponse> {
    const res = await fetch(`${API_BASE}/forecasts/${runId}/low-confidence?limit=${limit}`, {
      headers: DEFAULT_HEADERS,
    });
    return handleResponse<LowConfidenceResponse>(res);
  },

  /** Custom Newsvendor Inventory Optimization */
  async optimizeInventory(payload: InventoryOptimizeRequest): Promise<InventoryOptimizeResponse> {
    const res = await fetch(`${API_BASE}/inventory/optimize`, {
      method: "POST",
      headers: OPERATOR_HEADERS,
      body: JSON.stringify(payload),
    });
    return handleResponse<InventoryOptimizeResponse>(res);
  },

  /** Executive Evaluation Report */
  async getReport(runId: string = "RUN_EVAL_150_V1"): Promise<ReportSummaryResponse> {
    const res = await fetch(`${API_BASE}/reports/${runId}`, { headers: DEFAULT_HEADERS });
    return handleResponse<ReportSummaryResponse>(res);
  },

  /** Data Quality Audit Status */
  async getAuditStatus(): Promise<any> {
    const res = await fetch(`${API_BASE}/audit/status`);
    return handleResponse<any>(res);
  },
};
