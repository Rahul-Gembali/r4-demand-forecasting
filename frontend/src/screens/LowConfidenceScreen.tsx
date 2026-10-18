import React, { useState, useEffect } from "react";
import { LowConfidenceSKUItem } from "../types/api";
import { apiClient } from "../services/api";
import { Badge } from "../components/Badge";
import {
  AlertTriangle,
  ShieldAlert,
  Eye,
} from "lucide-react";

interface LowConfidenceScreenProps {
  runId: string;
  onSelectSKU: (skuId: string) => void;
}

export const LowConfidenceScreen: React.FC<LowConfidenceScreenProps> = ({
  runId,
  onSelectSKU,
}) => {
  const [items, setItems] = useState<LowConfidenceSKUItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .getLowConfidenceSKUs(runId, 10)
      .then((res) => {
        if (!isCancelled) {
          setItems(res.items);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || "Failed to load low-confidence products.");
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [runId]);

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 1rem", color: "#94A3B8" }}>
        <div style={{ fontSize: "1.2rem", fontWeight: 600 }}>Analyzing Cold-Start Confidence Index...</div>
        <p style={{ fontSize: "0.85rem", color: "#64748B" }}>Ranking products by prediction interval dispersion and analogue distance...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 1rem", color: "#F87171" }}>
        <AlertTriangle size={32} style={{ marginBottom: "0.5rem" }} />
        <div style={{ fontSize: "1.1rem", fontWeight: 600 }}>{error}</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Alert Banner */}
      <div
        style={{
          background: "linear-gradient(180deg, rgba(239, 68, 68, 0.12) 0%, rgba(239, 68, 68, 0.05) 100%)",
          border: "1px solid rgba(239, 68, 68, 0.3)",
          borderRadius: "14px",
          padding: "1.25rem 1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.85rem" }}>
          <ShieldAlert size={24} color="#F87171" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.25rem", color: "#F8FAFC", fontWeight: 700 }}>
                Low-Confidence SKU Triage & Diagnostic Review
              </h2>
              <Badge label="Human Review Required" variant="danger" size="sm" />
            </div>
            <p style={{ margin: "0.35rem 0 0 0", color: "#FECACA", fontSize: "0.85rem", lineHeight: "1.5" }}>
              Identified the <strong>10 highest-uncertainty cold-start products</strong> exhibiting wide conformal prediction intervals, distant historical donor analogues, or high category entropy. Merchant judgment is advised before placing binding purchase orders.
            </p>
          </div>
        </div>
      </div>

      {/* Methodology Explainer Card */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "12px",
          padding: "1.25rem",
          display: "flex",
          gap: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: "260px" }}>
          <h4 style={{ margin: "0 0 0.5rem 0", color: "#38BDF8", fontSize: "0.9rem" }}>
            Confidence Scoring Methodology (0 – 100)
          </h4>
          <p style={{ margin: 0, fontSize: "0.8rem", color: "#94A3B8", lineHeight: "1.5" }}>
            Cold-Start Confidence Index aggregates: <strong>(1) Conformal interval dispersion</strong> (ratio of 90% width to median demand), <strong>(2) Analogue proximity</strong> (Euclidean/cosine distance to top-5 nearest historical products), and <strong>(3) Category volatility</strong>.
          </p>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center", fontSize: "0.8rem" }}>
          <div style={{ padding: "0.5rem 0.75rem", background: "#030712", borderRadius: "8px", border: "1px solid #1F2937" }}>
            <div style={{ color: "#34D399", fontWeight: 700 }}>HIGH (75 – 100)</div>
            <div style={{ color: "#64748B", fontSize: "0.72rem" }}>Tight intervals, proven precedents</div>
          </div>
          <div style={{ padding: "0.5rem 0.75rem", background: "#030712", borderRadius: "8px", border: "1px solid #1F2937" }}>
            <div style={{ color: "#FBBF24", fontWeight: 700 }}>MEDIUM (50 – 74)</div>
            <div style={{ color: "#64748B", fontSize: "0.72rem" }}>Moderate variance, standard buffer</div>
          </div>
          <div style={{ padding: "0.5rem 0.75rem", background: "#030712", borderRadius: "8px", border: "1px solid #7F1D1D" }}>
            <div style={{ color: "#F87171", fontWeight: 700 }}>LOW (&lt; 50)</div>
            <div style={{ color: "#64748B", fontSize: "0.72rem" }}>Elevated uncertainty, manual sign-off</div>
          </div>
        </div>
      </div>

      {/* Ranked Diagnostic Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {items.map((item, idx) => (
          <div
            key={item.sku_id}
            style={{
              background: "#111827",
              border: "1px solid #1F2937",
              borderRadius: "12px",
              padding: "1.25rem 1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1.25rem",
              transition: "border-color 0.15s ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#F87171")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#1F2937")}
          >
            {/* Left Info: Rank, SKU, Name, Category */}
            <div style={{ display: "flex", alignItems: "center", gap: "1rem", minWidth: "280px" }}>
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  background: idx < 3 ? "#450A0A" : "#1F2937",
                  border: idx < 3 ? "1px solid #7F1D1D" : "1px solid #374151",
                  color: idx < 3 ? "#FCA5A5" : "#94A3B8",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 800,
                  fontSize: "0.95rem",
                  fontFamily: "'Geist Mono', monospace",
                  flexShrink: 0,
                }}
              >
                #{idx + 1}
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span style={{ fontWeight: 700, color: "#38BDF8", fontFamily: "'Geist Mono', monospace", fontSize: "1rem" }}>
                    {item.sku_id}
                  </span>
                  <Badge label={item.confidence_tier} variant="danger" size="sm" />
                </div>
                <div style={{ color: "#F8FAFC", fontWeight: 600, fontSize: "0.9rem", marginTop: "2px" }}>
                  {item.product_name}
                </div>
                <div style={{ color: "#94A3B8", fontSize: "0.78rem", marginTop: "2px" }}>
                  {item.category} • {item.subcategory} • ${item.base_price.toFixed(2)}
                </div>
              </div>
            </div>

            {/* Middle: Metrics & Diagnostic Reason */}
            <div style={{ display: "flex", gap: "1.5rem", alignItems: "center", flexWrap: "wrap" }}>
              <div>
                <span style={{ fontSize: "0.72rem", color: "#64748B", textTransform: "uppercase" }}>Confidence Score</span>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#F87171", fontFamily: "'Geist Mono', monospace" }}>
                  {item.confidence_score.toFixed(1)} / 100
                </div>
              </div>

              <div>
                <span style={{ fontSize: "0.72rem", color: "#64748B", textTransform: "uppercase" }}>8W Forecast</span>
                <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                  {item.forecast_cumulative_8w.toFixed(1)} units
                </div>
              </div>

              <div>
                <span style={{ fontSize: "0.72rem", color: "#64748B", textTransform: "uppercase" }}>Recommended Buy (Q*)</span>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#34D399", fontFamily: "'Geist Mono', monospace" }}>
                  {item.recommended_buy_quantity.toLocaleString()} units
                </div>
              </div>
            </div>

            {/* Diagnostic Explanation & Mitigation */}
            <div style={{ flex: 1, minWidth: "280px" }}>
              <div
                style={{
                  background: "#030712",
                  border: "1px solid #1F2937",
                  borderRadius: "8px",
                  padding: "0.6rem 0.85rem",
                  fontSize: "0.78rem",
                  color: "#CBD5E1",
                  lineHeight: "1.4",
                }}
              >
                {item.explanation_summary ||
                  "Wide conformal prediction interval (dispersion ratio > 2.4). Distant nearest historical analogues indicate sparse historical category coverage."}
              </div>

              <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.4rem", fontSize: "0.72rem", color: "#94A3B8" }}>
                <span>✓ Split order with supplier</span>
                <span>✓ Pre-order campaign test</span>
                <span>✓ 2-week early reorder</span>
              </div>
            </div>

            {/* Inspect Button */}
            <div>
              <button
                onClick={() => onSelectSKU(item.sku_id)}
                style={{
                  background: "rgba(56, 189, 248, 0.12)",
                  color: "#38BDF8",
                  border: "1px solid rgba(56, 189, 248, 0.3)",
                  borderRadius: "6px",
                  padding: "0.45rem 0.85rem",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                }}
              >
                <Eye size={14} />
                <span>Deep Dive</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
