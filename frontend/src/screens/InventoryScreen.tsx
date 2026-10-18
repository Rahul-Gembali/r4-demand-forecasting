import React, { useState } from "react";
import {
  ForecastRunResponse,
  InventoryOptimizeRequest,
  InventoryOptimizeResponse,
} from "../types/api";
import { apiClient } from "../services/api";
import { StatCard } from "../components/StatCard";
import { Badge } from "../components/Badge";
import {
  Boxes,
  Sliders,
  DollarSign,
  ShieldCheck,
  Play,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

interface InventoryScreenProps {
  runId: string;
  runSummary: ForecastRunResponse | null;
  onRefresh: () => void;
}

export const InventoryScreen: React.FC<InventoryScreenProps> = ({
  runId,
  runSummary,
  onRefresh,
}) => {
  // Scenario Form States
  const [scenarioName, setScenarioName] = useState<string>("HIGH_SERVICE_SIM");
  const [understockCostCu, setUnderstockCostCu] = useState<number>(30);
  const [overstockCostCo, setOverstockCostCo] = useState<number>(10);
  const [moq, setMoq] = useState<number>(50);
  const [casePack, setCasePack] = useState<number>(12);

  // Optimization Result States
  const [isOptimizing, setIsOptimizing] = useState<boolean>(false);
  const [optResult, setOptResult] = useState<InventoryOptimizeResponse | null>(null);
  const [optError, setOptError] = useState<string | null>(null);

  const criticalRatio = understockCostCu / (understockCostCu + overstockCostCo);

  const handleRunOptimization = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsOptimizing(true);
    setOptError(null);

    const payload: InventoryOptimizeRequest = {
      run_id: runId,
      scenario_name: scenarioName,
      understock_cost_cu: understockCostCu,
      overstock_cost_co: overstockCostCo,
      min_order_quantity: moq,
      case_pack_size: casePack,
    };

    try {
      const res = await apiClient.optimizeInventory(payload);
      setOptResult(res);
      setIsOptimizing(false);
      onRefresh(); // Refresh parent run totals
    } catch (err: any) {
      setOptError(err.message || "Optimization failed.");
      setIsOptimizing(false);
    }
  };

  const currentBuyUnits = optResult?.total_buy_units ?? runSummary?.total_recommended_buy_units ?? 74680;
  const currentCost = optResult?.total_expected_cost ?? runSummary?.total_expected_cost ?? 2893500;
  const currentFillRate = optResult?.average_fill_rate_pct ?? runSummary?.average_fill_rate_pct ?? 88.4;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Screen Title Banner */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "14px",
          padding: "1.25rem 1.5rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.35rem", color: "#F8FAFC", fontWeight: 700 }}>
              Initial Inventory & Buy Quantity Optimization
            </h2>
            <p style={{ margin: "4px 0 0 0", color: "#94A3B8", fontSize: "0.85rem" }}>
              Single-Period Newsvendor Decision Formulation with Minimum Order Quantity (MOQ) and Case Pack Constraints.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Badge label={`Horizon: 8-Week Cumulative`} variant="info" size="md" />
            <Badge label={`CR Formula: Cu / (Cu + Co)`} variant="purple" size="md" />
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem" }}>
        <StatCard
          title="Recommended Buy Volume"
          value={`${currentBuyUnits.toLocaleString()} units`}
          subtitle="Portfolio commitment"
          badge={{ text: optResult ? "Optimized" : "Base Scenario", variant: "success" }}
          icon={<Boxes size={18} />}
        />
        <StatCard
          title="Expected Total Risk Cost"
          value={`$${(currentCost / 1000).toFixed(1)}k`}
          subtitle="Understock + Overstock expected losses"
          badge={{ text: "Min Cost", variant: "warning" }}
          icon={<DollarSign size={18} />}
        />
        <StatCard
          title="Expected Fill Rate"
          value={`${currentFillRate.toFixed(1)}%`}
          subtitle="Customer order fulfillment probability"
          badge={{ text: "Target ≥ 85%", variant: "success" }}
          icon={<ShieldCheck size={18} />}
        />
        <StatCard
          title="Active Critical Ratio"
          value={criticalRatio.toFixed(3)}
          subtitle={`Cu=$${understockCostCu} / Co=$${overstockCostCo}`}
          badge={{ text: `${(criticalRatio * 100).toFixed(0)}th percentile`, variant: "purple" }}
          icon={<Sliders size={18} />}
        />
      </div>

      {/* Form: Interactive Scenario Optimizer */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "14px",
          padding: "1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <Sliders size={18} color="#38BDF8" />
          <h3 style={{ margin: 0, fontSize: "1.1rem", color: "#F8FAFC", fontWeight: 600 }}>
            Interactive Scenario Simulation Engine
          </h3>
        </div>
        <p style={{ color: "#94A3B8", fontSize: "0.82rem", margin: "0 0 1.25rem 0", lineHeight: "1.5" }}>
          Adjust the economic loss parameters and supply chain order constraints below to simulate how purchase commitments and financial exposure change across all 150 candidate SKUs:
        </p>

        <form onSubmit={handleRunOptimization}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
            {/* Scenario Name */}
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94A3B8", marginBottom: "0.35rem", fontWeight: 600 }}>
                Scenario Identifier
              </label>
              <input
                type="text"
                value={scenarioName}
                onChange={(e) => setScenarioName(e.target.value.toUpperCase())}
                required
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  background: "#030712",
                  border: "1px solid #1F2937",
                  borderRadius: "6px",
                  color: "#F8FAFC",
                  fontSize: "0.85rem",
                  fontFamily: "'Geist Mono', monospace",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Understock Cost Cu */}
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94A3B8", marginBottom: "0.35rem", fontWeight: 600 }}>
                Understock Cost (Cu) / Unit
              </label>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "#64748B" }}>$</span>
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={understockCostCu}
                  onChange={(e) => setUnderstockCostCu(Number(e.target.value))}
                  required
                  style={{
                    width: "100%",
                    padding: "0.5rem 0.75rem 0.5rem 1.75rem",
                    background: "#030712",
                    border: "1px solid #1F2937",
                    borderRadius: "6px",
                    color: "#F8FAFC",
                    fontSize: "0.85rem",
                    fontFamily: "'Geist Mono', monospace",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>

            {/* Overstock Cost Co */}
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94A3B8", marginBottom: "0.35rem", fontWeight: 600 }}>
                Overstock Cost (Co) / Unit
              </label>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "#64748B" }}>$</span>
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={overstockCostCo}
                  onChange={(e) => setOverstockCostCo(Number(e.target.value))}
                  required
                  style={{
                    width: "100%",
                    padding: "0.5rem 0.75rem 0.5rem 1.75rem",
                    background: "#030712",
                    border: "1px solid #1F2937",
                    borderRadius: "6px",
                    color: "#F8FAFC",
                    fontSize: "0.85rem",
                    fontFamily: "'Geist Mono', monospace",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>

            {/* Minimum Order Quantity (MOQ) */}
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94A3B8", marginBottom: "0.35rem", fontWeight: 600 }}>
                Minimum Order Qty (MOQ)
              </label>
              <input
                type="number"
                min="0"
                step="10"
                value={moq}
                onChange={(e) => setMoq(Number(e.target.value))}
                required
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  background: "#030712",
                  border: "1px solid #1F2937",
                  borderRadius: "6px",
                  color: "#F8FAFC",
                  fontSize: "0.85rem",
                  fontFamily: "'Geist Mono', monospace",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Case Pack Size */}
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94A3B8", marginBottom: "0.35rem", fontWeight: 600 }}>
                Case Pack Multiple
              </label>
              <input
                type="number"
                min="1"
                step="1"
                value={casePack}
                onChange={(e) => setCasePack(Number(e.target.value))}
                required
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  background: "#030712",
                  border: "1px solid #1F2937",
                  borderRadius: "6px",
                  color: "#F8FAFC",
                  fontSize: "0.85rem",
                  fontFamily: "'Geist Mono', monospace",
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>

          {/* Action Row */}
          <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "flex-end", gap: "0.75rem", alignItems: "center" }}>
            {optError && (
              <div style={{ color: "#F87171", fontSize: "0.82rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <AlertCircle size={14} />
                <span>{optError}</span>
              </div>
            )}
            <button
              type="submit"
              disabled={isOptimizing}
              style={{
                background: "#38BDF8",
                color: "#0B0F17",
                border: "none",
                borderRadius: "8px",
                padding: "0.6rem 1.25rem",
                fontSize: "0.85rem",
                fontWeight: 700,
                cursor: isOptimizing ? "not-allowed" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <Play size={15} />
              <span>{isOptimizing ? "Optimizing Portfolio..." : "Execute Newsvendor Optimization"}</span>
            </button>
          </div>
        </form>

        {/* Live Simulation Feedback */}
        {optResult && (
          <div
            style={{
              marginTop: "1.25rem",
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              borderRadius: "8px",
              padding: "0.85rem 1rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "0.5rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <CheckCircle2 size={16} color="#34D399" />
              <span style={{ fontSize: "0.85rem", color: "#E2E8F0" }}>
                Scenario <strong>{optResult.scenario_name}</strong> executed: {optResult.total_skus_optimized} SKUs optimized.
              </span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "#34D399", fontWeight: 600 }}>
              Total Units: {optResult.total_buy_units.toLocaleString()} | Cost: ${(optResult.total_expected_cost / 1000).toFixed(1)}k | Fill Rate: {optResult.average_fill_rate_pct.toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {/* Scenario Recommendations Table */}
      {optResult && (
        <div
          style={{
            background: "#111827",
            border: "1px solid #1F2937",
            borderRadius: "12px",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "1rem 1.25rem", borderBottom: "1px solid #1F2937", display: "flex", justifyContent: "space-between" }}>
            <h4 style={{ margin: 0, fontSize: "0.95rem", color: "#F8FAFC" }}>
              Optimized SKU Allocations (Sample First 15 SKUs)
            </h4>
            <span style={{ fontSize: "0.75rem", color: "#64748B" }}>
              Scenario: {optResult.scenario_name}
            </span>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", textAlign: "left" }}>
              <thead>
                <tr style={{ background: "#0F172A", borderBottom: "1px solid #1F2937", color: "#94A3B8" }}>
                  <th style={{ padding: "0.6rem 1rem" }}>SKU ID</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Scenario</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Recommended Buy (Q*)</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Critical Ratio</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Expected Cost</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Expected Fill Rate</th>
                </tr>
              </thead>
              <tbody>
                {optResult.recommendations.slice(0, 15).map((rec) => (
                  <tr key={rec.sku_id} style={{ borderBottom: "1px solid #1F2937" }}>
                    <td style={{ padding: "0.6rem 1rem", fontWeight: 600, color: "#38BDF8", fontFamily: "'Geist Mono', monospace" }}>
                      {rec.sku_id}
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", color: "#E2E8F0" }}>{rec.scenario}</td>
                    <td style={{ padding: "0.6rem 0.75rem", fontWeight: 700, color: "#34D399", fontFamily: "'Geist Mono', monospace" }}>
                      {rec.recommended_buy_quantity.toLocaleString()} units
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", color: "#FBBF24", fontFamily: "'Geist Mono', monospace" }}>
                      {rec.critical_ratio.toFixed(3)}
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", color: "#CBD5E1", fontFamily: "'Geist Mono', monospace" }}>
                      ${rec.expected_total_cost.toFixed(2)}
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", color: "#34D399", fontWeight: 600, fontFamily: "'Geist Mono', monospace" }}>
                      {rec.expected_fill_rate_pct.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
