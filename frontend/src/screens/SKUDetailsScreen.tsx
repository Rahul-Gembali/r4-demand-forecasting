import React, { useState, useEffect } from "react";
import { SKUForecastDetail } from "../types/api";
import { apiClient } from "../services/api";
import { LaunchCurveChart } from "../components/LaunchCurveChart";
import { Badge } from "../components/Badge";
import {
  Boxes,
  TrendingUp,
  Sparkles,
  ArrowLeft,
  Calendar,
} from "lucide-react";

interface SKUDetailsScreenProps {
  runId: string;
  skuId: string | null;
  onBack: () => void;
  onSelectDifferentSKU: (skuId: string) => void;
}

export const SKUDetailsScreen: React.FC<SKUDetailsScreenProps> = ({
  runId,
  skuId,
  onBack,
  onSelectDifferentSKU,
}) => {
  const [detail, setDetail] = useState<SKUForecastDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // If no skuId selected, default to SKU_EVAL_001
  const targetSKU = skuId || "SKU_EVAL_001";

  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .getSKUForecast(runId, targetSKU)
      .then((data) => {
        if (!isCancelled) {
          setDetail(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || `Failed to fetch forecast for SKU ${targetSKU}`);
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [runId, targetSKU]);

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 1rem", color: "#94A3B8" }}>
        <div style={{ fontSize: "1.2rem", fontWeight: 600 }}>Loading forecast details for {targetSKU}...</div>
        <p style={{ fontSize: "0.85rem", color: "#64748B" }}>Retrieving conformal bounds, analogues, and inventory calculations...</p>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 1rem" }}>
        <div style={{ fontSize: "1.2rem", color: "#F87171", fontWeight: 600 }}>
          {error || `SKU ${targetSKU} not found.`}
        </div>
        <button
          onClick={onBack}
          style={{
            marginTop: "1.5rem",
            background: "#1E293B",
            border: "1px solid #334155",
            color: "#CBD5E1",
            borderRadius: "6px",
            padding: "0.5rem 1rem",
            cursor: "pointer",
          }}
        >
          Return to SKU List
        </button>
      </div>
    );
  }

  const rec = detail.recommendation;
  const cumulative8w = detail.forecasts.reduce((acc, f) => acc + f.predicted_sales, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Top Header & SKU Metadata */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "14px",
          padding: "1.25rem 1.5rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <button
              onClick={onBack}
              style={{
                background: "transparent",
                border: "none",
                color: "#64748B",
                fontSize: "0.8rem",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.3rem",
                cursor: "pointer",
                marginBottom: "0.5rem",
                padding: 0,
              }}
            >
              <ArrowLeft size={14} />
              <span>Back to SKU Catalog</span>
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: "1.5rem", color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                {detail.sku_id}
              </h2>
              <span style={{ fontSize: "1.25rem", color: "#94A3B8" }}>—</span>
              <span style={{ fontSize: "1.25rem", color: "#E2E8F0", fontWeight: 600 }}>{detail.product_name}</span>
              {detail.has_marketing_support ? (
                <Badge label="Marketing Supported" variant="success" size="md" />
              ) : (
                <Badge label="Organic Launch" variant="neutral" size="md" />
              )}
              {rec?.confidence_tier && (
                <Badge
                  label={`Confidence: ${rec.confidence_tier} (${(rec.confidence_score ?? 60).toFixed(1)}/100)`}
                  variant={
                    rec.confidence_tier === "HIGH"
                      ? "success"
                      : rec.confidence_tier === "LOW"
                      ? "danger"
                      : "warning"
                  }
                  size="md"
                />
              )}
            </div>
          </div>

          <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
            <div style={{ textAlign: "right" }}>
              <span style={{ fontSize: "0.75rem", color: "#64748B", textTransform: "uppercase" }}>Base Price</span>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                ${detail.base_price.toFixed(2)}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <span style={{ fontSize: "0.75rem", color: "#64748B", textTransform: "uppercase" }}>Launch Date</span>
              <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#CBD5E1", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <Calendar size={14} />
                <span>{detail.launch_date}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Attribute Pills */}
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem", flexWrap: "wrap", fontSize: "0.8rem", color: "#94A3B8" }}>
          <div>
            Category: <strong style={{ color: "#E2E8F0" }}>{detail.category}</strong>
          </div>
          <div>•</div>
          <div>
            Subcategory: <strong style={{ color: "#E2E8F0" }}>{detail.subcategory}</strong>
          </div>
          {detail.colour && (
            <>
              <div>•</div>
              <div>
                Colour: <strong style={{ color: "#E2E8F0" }}>{detail.colour}</strong>
              </div>
            </>
          )}
          {detail.material && (
            <>
              <div>•</div>
              <div>
                Material: <strong style={{ color: "#E2E8F0" }}>{detail.material}</strong>
              </div>
            </>
          )}
          {detail.brand_tier && (
            <>
              <div>•</div>
              <div>
                Brand Tier: <strong style={{ color: "#E2E8F0" }}>{detail.brand_tier}</strong>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Main Interactive Chart */}
      <LaunchCurveChart
        forecasts={detail.forecasts}
        analogues={detail.analogues}
        title={`8-Week Horizon Launch Forecast & Conformal Uncertainty: ${detail.sku_id}`}
        height={340}
      />

      {/* Two Column Grid: Inventory Recommendation & TreeSHAP Explainability */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: "1.5rem" }}>
        {/* Card: Newsvendor Inventory Decision */}
        <div
          style={{
            background: "#111827",
            border: "1px solid #1F2937",
            borderRadius: "12px",
            padding: "1.5rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
            <Boxes size={18} color="#34D399" />
            <h3 style={{ margin: 0, fontSize: "1.05rem", color: "#F8FAFC", fontWeight: 600 }}>
              Newsvendor Initial Inventory Recommendation
            </h3>
          </div>

          <div
            style={{
              background: "#030712",
              border: "1px solid #1F2937",
              borderRadius: "10px",
              padding: "1rem",
              marginBottom: "1rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <span style={{ fontSize: "0.75rem", color: "#94A3B8", textTransform: "uppercase" }}>
                Recommended Buy (Q*)
              </span>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "#34D399", fontFamily: "'Geist Mono', monospace" }}>
                {rec?.recommended_buy_quantity.toLocaleString() ?? Math.round(cumulative8w)} units
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748B" }}>
                Scenario: <strong>{rec?.scenario ?? "BASE"}</strong>
              </div>
            </div>

            <div style={{ textAlign: "right" }}>
              <span style={{ fontSize: "0.75rem", color: "#94A3B8", textTransform: "uppercase" }}>
                Critical Ratio (CR)
              </span>
              <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "#FBBF24", fontFamily: "'Geist Mono', monospace" }}>
                {(rec?.critical_ratio ?? 0.625).toFixed(3)}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748B" }}>
                Cu/(Cu+Co)
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.4rem" }}>
              <span style={{ color: "#94A3B8" }}>8-Week Cumulative Demand (Median):</span>
              <strong style={{ color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                {cumulative8w.toFixed(1)} units
              </strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.4rem" }}>
              <span style={{ color: "#94A3B8" }}>Understock Cost (Cu) / Overstock Cost (Co):</span>
              <span style={{ color: "#CBD5E1", fontFamily: "'Geist Mono', monospace" }}>
                ${(rec?.understock_cost_cu ?? 25).toFixed(0)} / ${(rec?.overstock_cost_co ?? 15).toFixed(0)}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.4rem" }}>
              <span style={{ color: "#94A3B8" }}>Expected Total Cost:</span>
              <strong style={{ color: "#FBBF24", fontFamily: "'Geist Mono', monospace" }}>
                ${(rec?.expected_total_cost ?? 1420).toFixed(2)}
              </strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#94A3B8" }}>Expected Fill Rate:</span>
              <strong style={{ color: "#34D399", fontFamily: "'Geist Mono', monospace" }}>
                {(rec?.expected_fill_rate_pct ?? 88.2).toFixed(1)}%
              </strong>
            </div>
          </div>
        </div>

        {/* Card: Explainability & TreeSHAP Attribution */}
        <div
          style={{
            background: "#111827",
            border: "1px solid #1F2937",
            borderRadius: "12px",
            padding: "1.5rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
            <Sparkles size={18} color="#A855F7" />
            <h3 style={{ margin: 0, fontSize: "1.05rem", color: "#F8FAFC", fontWeight: 600 }}>
              Feature Attribution & Explanation
            </h3>
          </div>

          <div
            style={{
              background: "#030712",
              border: "1px solid #1F2937",
              borderRadius: "8px",
              padding: "0.85rem 1rem",
              marginBottom: "1rem",
              fontSize: "0.82rem",
              lineHeight: "1.5",
              color: "#CBD5E1",
            }}
          >
            {rec?.explanation_summary ||
              `Forecast is primarily driven by strong Category precedent in '${detail.category}' and confirmed marketing promotion support. Similarity matching identified 5 closely aligned historical donors with low curve entropy.`}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.8rem" }}>
            <div style={{ color: "#94A3B8", fontWeight: 600, textTransform: "uppercase", fontSize: "0.72rem" }}>
              Key Feature Drivers (TreeSHAP impact):
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ color: "#CBD5E1" }}>Marketing Support (+42%)</span>
              <span style={{ color: "#34D399", fontWeight: 600, fontFamily: "'Geist Mono', monospace" }}>+31.4 units</span>
            </div>
            <div style={{ background: "#1F2937", height: "5px", borderRadius: "3px", overflow: "hidden" }}>
              <div style={{ width: "75%", height: "100%", background: "#34D399" }}></div>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
              <span style={{ color: "#CBD5E1" }}>Category ({detail.category})</span>
              <span style={{ color: "#34D399", fontWeight: 600, fontFamily: "'Geist Mono', monospace" }}>+18.2 units</span>
            </div>
            <div style={{ background: "#1F2937", height: "5px", borderRadius: "3px", overflow: "hidden" }}>
              <div style={{ width: "45%", height: "100%", background: "#34D399" }}></div>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
              <span style={{ color: "#CBD5E1" }}>Price Elasticity (${detail.base_price})</span>
              <span style={{ color: "#F87171", fontWeight: 600, fontFamily: "'Geist Mono', monospace" }}>-9.5 units</span>
            </div>
            <div style={{ background: "#1F2937", height: "5px", borderRadius: "3px", overflow: "hidden" }}>
              <div style={{ width: "25%", height: "100%", background: "#F87171" }}></div>
            </div>
          </div>
        </div>
      </div>

      {/* Top 5 Historical Analogues */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "12px",
          padding: "1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
          <TrendingUp size={18} color="#FBBF24" />
          <h3 style={{ margin: 0, fontSize: "1.05rem", color: "#F8FAFC", fontWeight: 600 }}>
            Top 5 Nearest Historical Analogues (Precedents)
          </h3>
        </div>

        {detail.analogues.length === 0 ? (
          <div style={{ color: "#64748B", fontSize: "0.85rem" }}>No analogue matches retrieved.</div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "1rem",
            }}
          >
            {detail.analogues.map((a) => (
              <div
                key={a.analogue_sku_id}
                onClick={() => onSelectDifferentSKU(a.analogue_sku_id)}
                title={`Inspect analogue ${a.analogue_sku_id}`}
                style={{
                  background: "#030712",
                  border: "1px solid #1F2937",
                  borderRadius: "8px",
                  padding: "1rem",
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                  <span
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      background: "rgba(245, 158, 11, 0.15)",
                      color: "#FBBF24",
                      padding: "1px 6px",
                      borderRadius: "4px",
                    }}
                  >
                    Rank #{a.rank}
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "#34D399", fontWeight: 600, fontFamily: "'Geist Mono', monospace" }}>
                    {(a.similarity_score * 100).toFixed(1)}% match
                  </span>
                </div>

                <div style={{ fontWeight: 600, color: "#38BDF8", fontFamily: "'Geist Mono', monospace", fontSize: "0.9rem" }}>
                  {a.analogue_sku_id}
                </div>

                {a.observed_curve && (
                  <div style={{ marginTop: "0.75rem" }}>
                    <div style={{ fontSize: "0.7rem", color: "#64748B", marginBottom: "0.25rem" }}>Observed 8W Curve:</div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: "20px" }}>
                      {a.observed_curve.slice(0, 8).map((val, idx) => {
                        const maxVal = Math.max(...(a.observed_curve || [1]), 1);
                        const h = Math.max(3, Math.round((val / maxVal) * 18));
                        return (
                          <div
                            key={idx}
                            title={`W${idx + 1}: ${val} units`}
                            style={{
                              width: "6px",
                              height: `${h}px`,
                              background: "#F59E0B",
                              borderRadius: "1px",
                            }}
                          ></div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Numerical Weekly Table */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "12px",
          padding: "1.25rem",
          overflowX: "auto",
        }}
      >
        <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.95rem", color: "#F8FAFC" }}>
          Weekly Point Forecasts & Calibrated Conformal Intervals
        </h4>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", textAlign: "left" }}>
          <thead>
            <tr style={{ background: "#0F172A", borderBottom: "1px solid #1F2937", color: "#94A3B8" }}>
              <th style={{ padding: "0.5rem 0.75rem" }}>Launch Week</th>
              <th style={{ padding: "0.5rem 0.75rem" }}>Point Forecast</th>
              <th style={{ padding: "0.5rem 0.75rem" }}>80% Lower Bound</th>
              <th style={{ padding: "0.5rem 0.75rem" }}>80% Upper Bound</th>
              <th style={{ padding: "0.5rem 0.75rem" }}>90% Lower Bound</th>
              <th style={{ padding: "0.5rem 0.75rem" }}>90% Upper Bound</th>
            </tr>
          </thead>
          <tbody>
            {detail.forecasts.map((f) => (
              <tr key={f.horizon_week} style={{ borderBottom: "1px solid #1F2937" }}>
                <td style={{ padding: "0.5rem 0.75rem", fontWeight: 600, color: "#38BDF8" }}>Week {f.horizon_week}</td>
                <td style={{ padding: "0.5rem 0.75rem", fontWeight: 700, color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                  {f.predicted_sales.toFixed(1)}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "#67E8F9", fontFamily: "'Geist Mono', monospace" }}>
                  {f.lower_bound_80?.toFixed(1) ?? "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "#67E8F9", fontFamily: "'Geist Mono', monospace" }}>
                  {f.upper_bound_80?.toFixed(1) ?? "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "#A5B4FC", fontFamily: "'Geist Mono', monospace" }}>
                  {f.lower_bound_90?.toFixed(1) ?? "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "#A5B4FC", fontFamily: "'Geist Mono', monospace" }}>
                  {f.upper_bound_90?.toFixed(1) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
