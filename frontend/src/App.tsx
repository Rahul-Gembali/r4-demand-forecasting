import { useState, useEffect, useCallback } from "react";
import {
  ForecastRunResponse,
  ModelVersionItem,
  ReportSummaryResponse,
} from "./types/api";
import { apiClient } from "./services/api";
import { Navigation, ScreenId } from "./components/Navigation";
import { OverviewScreen } from "./screens/OverviewScreen";
import { SKUForecastingScreen } from "./screens/SKUForecastingScreen";
import { SKUDetailsScreen } from "./screens/SKUDetailsScreen";
import { InventoryScreen } from "./screens/InventoryScreen";
import { LowConfidenceScreen } from "./screens/LowConfidenceScreen";
import { EvaluationScreen } from "./screens/EvaluationScreen";
import { DataQualityScreen } from "./screens/DataQualityScreen";

export default function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("overview");
  const [selectedSKUId, setSelectedSKUId] = useState<string | null>("SKU_EVAL_001");
  const [runId] = useState<string>("RUN_EVAL_150_V1");

  // Global State
  const [runSummary, setRunSummary] = useState<ForecastRunResponse | null>(null);
  const [report, setReport] = useState<ReportSummaryResponse | null>(null);
  const [models, setModels] = useState<ModelVersionItem[]>([]);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const fetchGlobalData = useCallback(async () => {
    try {
      // 1. Health check
      try {
        await apiClient.checkHealth();
        setIsBackendHealthy(true);
      } catch {
        setIsBackendHealthy(false);
      }

      // 2. Load run summary, models, and report in parallel
      const [summaryRes, reportRes, modelsRes] = await Promise.allSettled([
        apiClient.getForecastRun(runId),
        apiClient.getReport(runId),
        apiClient.getModels(),
      ]);

      if (summaryRes.status === "fulfilled") {
        setRunSummary(summaryRes.value);
      }
      if (reportRes.status === "fulfilled") {
        setReport(reportRes.value);
      }
      if (modelsRes.status === "fulfilled") {
        setModels(modelsRes.value);
      }
    } catch (err) {
      console.error("Error loading application state:", err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [runId]);

  useEffect(() => {
    fetchGlobalData();
  }, [fetchGlobalData]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    fetchGlobalData();
  };

  const handleSelectSKU = (skuId: string) => {
    setSelectedSKUId(skuId);
    setActiveScreen("details");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#0B0F17",
        color: "#F8FAFC",
        fontFamily: "'Geist', -apple-system, BlinkMacSystemFont, sans-serif",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Persistent Navigation Header */}
      <Navigation
        activeScreen={activeScreen}
        onScreenChange={(screen) => {
          setActiveScreen(screen);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
        selectedSKUId={selectedSKUId}
        runId={runId}
        isBackendHealthy={isBackendHealthy}
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
      />

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: "1.75rem", maxWidth: "1400px", margin: "0 auto", width: "100%", boxSizing: "border-box" }}>
        {activeScreen === "overview" && (
          <OverviewScreen
            runSummary={runSummary}
            report={report}
            models={models}
            onNavigate={(screen) => {
              setActiveScreen(screen);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            isLoading={isLoading}
          />
        )}

        {activeScreen === "forecasting" && (
          <SKUForecastingScreen
            runId={runId}
            onSelectSKU={handleSelectSKU}
          />
        )}

        {activeScreen === "details" && (
          <SKUDetailsScreen
            runId={runId}
            skuId={selectedSKUId}
            onBack={() => setActiveScreen("forecasting")}
            onSelectDifferentSKU={handleSelectSKU}
          />
        )}

        {activeScreen === "inventory" && (
          <InventoryScreen
            runId={runId}
            runSummary={runSummary}
            onRefresh={handleRefresh}
          />
        )}

        {activeScreen === "low_confidence" && (
          <LowConfidenceScreen
            runId={runId}
            onSelectSKU={handleSelectSKU}
          />
        )}

        {activeScreen === "evaluation" && (
          <EvaluationScreen
            report={report}
            isLoading={isLoading}
          />
        )}

        {activeScreen === "data_quality" && (
          <DataQualityScreen report={report} />
        )}
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid #1E293B",
          padding: "1rem 1.75rem",
          background: "#080C14",
          color: "#64748B",
          fontSize: "0.78rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.5rem",
        }}
      >
        <div>
          <span>R4 New Product Demand Forecasting Platform • Enterprise Production Release v0.9.0</span>
        </div>
        <div style={{ display: "flex", gap: "1rem" }}>
          <span>CatBoost GBDT Cold-Start Engine</span>
          <span>•</span>
          <span>Conformal Split-Quantile Calibration</span>
          <span>•</span>
          <span>Single-Period Newsvendor Optimizer</span>
        </div>
      </footer>
    </div>
  );
}
