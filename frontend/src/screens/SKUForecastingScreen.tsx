import React, { useState, useEffect } from "react";
import { SKUForecastListItem } from "../types/api";
import { apiClient } from "../services/api";
import { Badge } from "../components/Badge";
import { Search, Filter, ChevronLeft, ChevronRight, Eye } from "lucide-react";

interface SKUForecastingScreenProps {
  runId: string;
  onSelectSKU: (skuId: string) => void;
}

const CATEGORIES = ["ALL", "Footwear", "Apparel", "Outerwear", "Accessories", "Equipment"];

export const SKUForecastingScreen: React.FC<SKUForecastingScreenProps> = ({
  runId,
  onSelectSKU,
}) => {
  const [skus, setSkus] = useState<SKUForecastListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [page, setPage] = useState<number>(0);
  const [pageSize] = useState<number>(25);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch SKUs when search, category, or page changes
  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);
    setError(null);

    apiClient
      .listSKUForecasts(runId, selectedCategory, searchTerm, pageSize, page * pageSize)
      .then((res) => {
        if (!isCancelled) {
          setSkus(res.items);
          setTotalCount(res.total);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || "Failed to load SKU forecasts.");
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [runId, selectedCategory, searchTerm, page, pageSize]);

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Controls Bar: Search & Category Filters */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "12px",
          padding: "1rem 1.25rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        {/* Search Input */}
        <div style={{ position: "relative", minWidth: "300px", flex: 1, maxWidth: "450px" }}>
          <Search
            size={16}
            color="#64748B"
            style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }}
          />
          <input
            type="text"
            placeholder="Search SKU ID, product name, subcategory..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(0);
            }}
            style={{
              width: "100%",
              padding: "0.55rem 0.75rem 0.55rem 2.25rem",
              background: "#030712",
              border: "1px solid #1F2937",
              borderRadius: "8px",
              color: "#F8FAFC",
              fontSize: "0.85rem",
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>

        {/* Category Filter Pills */}
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.78rem", color: "#64748B", marginRight: "0.25rem", display: "flex", alignItems: "center", gap: "0.2rem" }}>
            <Filter size={13} />
            <span>Category:</span>
          </span>
          {CATEGORIES.map((cat) => {
            const isSelected = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCategory(cat);
                  setPage(0);
                }}
                style={{
                  padding: "0.35rem 0.75rem",
                  borderRadius: "6px",
                  fontSize: "0.78rem",
                  fontWeight: isSelected ? 600 : 400,
                  background: isSelected ? "rgba(56, 189, 248, 0.15)" : "#0B0F17",
                  border: isSelected ? "1px solid #38BDF8" : "1px solid #1F2937",
                  color: isSelected ? "#38BDF8" : "#94A3B8",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </div>

      {/* Table Container */}
      <div
        style={{
          background: "#111827",
          border: "1px solid #1F2937",
          borderRadius: "12px",
          overflow: "hidden",
          boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.2)",
        }}
      >
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
            <thead>
              <tr style={{ background: "#0F172A", borderBottom: "1px solid #1F2937", color: "#94A3B8" }}>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>SKU & Product</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Category / Subcategory</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Price</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Marketing</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>8W Projected</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Weekly Trend (W1-W8)</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Recommended Buy (Q*)</th>
                <th style={{ padding: "0.75rem 0.75rem", fontWeight: 600 }}>Confidence</th>
                <th style={{ padding: "0.75rem 1rem", fontWeight: 600, textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={9} style={{ padding: "3rem", textAlign: "center", color: "#94A3B8" }}>
                    Loading SKUs from database...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={9} style={{ padding: "3rem", textAlign: "center", color: "#F87171" }}>
                    {error}
                  </td>
                </tr>
              ) : skus.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ padding: "3rem", textAlign: "center", color: "#64748B" }}>
                    No SKUs matched the search criteria.
                  </td>
                </tr>
              ) : (
                skus.map((sku) => {
                  const maxWk = Math.max(...sku.weekly_forecasts, 1);
                  return (
                    <tr
                      key={sku.sku_id}
                      style={{
                        borderBottom: "1px solid #1F2937",
                        transition: "background 0.12s ease",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#1E293B")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      {/* SKU & Product */}
                      <td style={{ padding: "0.75rem 1rem" }}>
                        <div style={{ fontWeight: 600, color: "#38BDF8", fontFamily: "'Geist Mono', monospace" }}>
                          {sku.sku_id}
                        </div>
                        <div style={{ color: "#E2E8F0", fontSize: "0.8rem", marginTop: "2px" }}>
                          {sku.product_name}
                        </div>
                      </td>

                      {/* Category */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        <div style={{ color: "#F8FAFC" }}>{sku.category}</div>
                        <div style={{ color: "#64748B", fontSize: "0.75rem" }}>{sku.subcategory}</div>
                      </td>

                      {/* Price */}
                      <td style={{ padding: "0.75rem 0.75rem", color: "#E2E8F0", fontFamily: "'Geist Mono', monospace" }}>
                        ${sku.base_price.toFixed(2)}
                      </td>

                      {/* Marketing */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        {sku.has_marketing_support ? (
                          <Badge label="Supported" variant="success" size="sm" />
                        ) : (
                          <Badge label="Organic" variant="neutral" size="sm" />
                        )}
                      </td>

                      {/* 8W Projected */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        <div style={{ fontWeight: 700, color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
                          {sku.total_projected_sales.toFixed(1)}
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "#64748B" }}>units</div>
                      </td>

                      {/* Sparkline mini-bars */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: "24px" }}>
                          {sku.weekly_forecasts.map((w, i) => {
                            const barHeight = Math.max(3, Math.round((w / maxWk) * 22));
                            return (
                              <div
                                key={i}
                                title={`W${i + 1}: ${w.toFixed(1)} units`}
                                style={{
                                  width: "6px",
                                  height: `${barHeight}px`,
                                  background: "#38BDF8",
                                  borderRadius: "1px",
                                  opacity: 0.8,
                                }}
                              ></div>
                            );
                          })}
                        </div>
                      </td>

                      {/* Recommended Buy */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        <div style={{ fontWeight: 700, color: "#34D399", fontFamily: "'Geist Mono', monospace" }}>
                          {sku.recommended_buy_quantity.toLocaleString()}
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "#64748B" }}>
                          fill: {(sku.expected_fill_rate_pct ?? 85).toFixed(0)}%
                        </div>
                      </td>

                      {/* Confidence */}
                      <td style={{ padding: "0.75rem 0.75rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <Badge
                            label={sku.confidence_tier}
                            variant={
                              sku.confidence_tier === "HIGH"
                                ? "success"
                                : sku.confidence_tier === "LOW"
                                ? "danger"
                                : "warning"
                            }
                            size="sm"
                          />
                          {sku.confidence_score !== null && (
                            <span style={{ fontSize: "0.75rem", color: "#94A3B8", fontFamily: "'Geist Mono', monospace" }}>
                              {sku.confidence_score.toFixed(1)}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Action */}
                      <td style={{ padding: "0.75rem 1rem", textAlign: "right" }}>
                        <button
                          onClick={() => onSelectSKU(sku.sku_id)}
                          style={{
                            background: "rgba(56, 189, 248, 0.12)",
                            color: "#38BDF8",
                            border: "1px solid rgba(56, 189, 248, 0.3)",
                            borderRadius: "6px",
                            padding: "0.35rem 0.65rem",
                            fontSize: "0.78rem",
                            fontWeight: 600,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.3rem",
                          }}
                        >
                          <Eye size={13} />
                          <span>Detail</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div
          style={{
            padding: "0.75rem 1rem",
            background: "#0F172A",
            borderTop: "1px solid #1F2937",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: "0.8rem",
            color: "#94A3B8",
          }}
        >
          <div>
            Showing <strong>{skus.length > 0 ? page * pageSize + 1 : 0}</strong> to{" "}
            <strong>{Math.min((page + 1) * pageSize, totalCount)}</strong> of <strong>{totalCount}</strong> candidate SKUs
          </div>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || isLoading}
              style={{
                background: "#1E293B",
                border: "1px solid #334155",
                color: page === 0 ? "#475569" : "#CBD5E1",
                borderRadius: "6px",
                padding: "0.35rem 0.65rem",
                cursor: page === 0 ? "not-allowed" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.2rem",
              }}
            >
              <ChevronLeft size={14} />
              <span>Previous</span>
            </button>

            <span style={{ padding: "0 0.5rem" }}>
              Page <strong>{page + 1}</strong> of <strong>{totalPages || 1}</strong>
            </span>

            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1 || isLoading}
              style={{
                background: "#1E293B",
                border: "1px solid #334155",
                color: page >= totalPages - 1 ? "#475569" : "#CBD5E1",
                borderRadius: "6px",
                padding: "0.35rem 0.65rem",
                cursor: page >= totalPages - 1 ? "not-allowed" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.2rem",
              }}
            >
              <span>Next</span>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
