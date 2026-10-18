import React, { useState, useEffect } from "react";

interface AuditSummary {
  directory_path?: string;
  total_files_scanned?: number;
  blockers?: string[];
  summary_findings?: {
    total_files?: number;
    total_rows?: number;
  };
}

export default function App() {
  const [auditData, setAuditData] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [healthStatus, setHealthStatus] = useState<string>("Checking...");

  useEffect(() => {
    // Probe backend health
    fetch("/api/v1/health")
      .then((res) => res.json())
      .then((data) => setHealthStatus(data.status))
      .catch(() => setHealthStatus("Offline (Backend starting)"));

    // Probe data audit status
    fetch("/api/v1/audit/status")
      .then((res) => res.json())
      .then((data) => {
        setAuditData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Audit fetch error", err);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#0B0F17", padding: "2rem" }}>
      {/* Header */}
      <header style={{ borderBottom: "1px solid #1E293B", paddingBottom: "1.5rem", marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span style={{ fontSize: "0.8rem", color: "#6366F1", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>
              Phase 1 — Project Initialization & Discovery
            </span>
            <h1 style={{ fontSize: "1.75rem", margin: "0.25rem 0 0 0", color: "#F8FAFC" }}>
              R4 New Product Demand Forecasting
            </h1>
            <p style={{ margin: "0.25rem 0 0 0", color: "#94A3B8", fontSize: "0.95rem" }}>
              Cold-start 8-week horizon forecasting for 150 new retail SKUs across store clusters.
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", background: "#1E293B", padding: "0.4rem 0.8rem", borderRadius: "9999px" }}>
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: healthStatus === "healthy" ? "#10B981" : "#F59E0B" }}></span>
              <span style={{ fontSize: "0.85rem", color: "#CBD5E1" }}>Backend: {healthStatus}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.5rem" }}>
        {/* Card: Target Constraints */}
        <div style={{ background: "#111827", border: "1px solid #1F2937", borderRadius: "12px", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem", color: "#E2E8F0", marginTop: 0 }}>Target Evaluation Specs</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.5rem" }}>
              <span style={{ color: "#94A3B8" }}>Evaluation SKUs:</span>
              <strong style={{ color: "#F8FAFC" }}>150 New Products (Cold-Start)</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.5rem" }}>
              <span style={{ color: "#94A3B8" }}>Forecast Horizon:</span>
              <strong style={{ color: "#F8FAFC" }}>First 8 Weeks (W1 - W8)</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.5rem" }}>
              <span style={{ color: "#94A3B8" }}>Historical Donors:</span>
              <strong style={{ color: "#F8FAFC" }}>~1,200 Mature SKUs</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #1F2937", paddingBottom: "0.5rem" }}>
              <span style={{ color: "#94A3B8" }}>Primary Metric:</span>
              <strong style={{ color: "#10B981" }}>WAPE (Weighted Abs % Error)</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#94A3B8" }}>Secondary Metrics:</span>
              <strong style={{ color: "#38BDF8" }}>RMSE, MAE, Bias %</strong>
            </div>
          </div>
        </div>

        {/* Card: Phase 1 Blocker Registry */}
        <div style={{ background: "#111827", border: "1px solid #1F2937", borderRadius: "12px", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem", color: "#F87171", marginTop: 0 }}>Phase 1 Blocker Registry</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", padding: "0.75rem", borderRadius: "8px" }}>
              <div style={{ fontWeight: 700, color: "#FECACA", fontSize: "0.85rem" }}>BLK-001: Raw Dataset Pending Ingestion</div>
              <p style={{ margin: "0.25rem 0 0 0", color: "#FCA5A5", fontSize: "0.8rem" }}>
                Zero CSV/Parquet files found in <code>data/raw/</code>. Awaiting source data placement.
              </p>
            </div>
            <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", padding: "0.75rem", borderRadius: "8px" }}>
              <div style={{ fontWeight: 700, color: "#FECACA", fontSize: "0.85rem" }}>BLK-002: Official evaluate.py Pending</div>
              <p style={{ margin: "0.25rem 0 0 0", color: "#FCA5A5", fontSize: "0.8rem" }}>
                Official evaluator missing. Using formal mathematical specification in <code>docs/EVALUATION_SPEC.md</code>.
              </p>
            </div>
          </div>
        </div>

        {/* Card: Data Ingestion & Verification */}
        <div style={{ background: "#111827", border: "1px solid #1F2937", borderRadius: "12px", padding: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem", color: "#E2E8F0", marginTop: 0 }}>Automated Inspection Tool</h2>
          <p style={{ color: "#94A3B8", fontSize: "0.85rem", lineHeight: "1.5" }}>
            Once raw files are dropped into <code>data/raw/</code>, execute the discovery pipeline to validate schemas without manual assumptions:
          </p>
          <div style={{ background: "#030712", padding: "0.75rem", borderRadius: "6px", border: "1px solid #1E293B", fontFamily: "monospace", fontSize: "0.8rem", color: "#38BDF8" }}>
            python scripts/inspect_data.py --data-dir data/raw
          </div>
          <div style={{ marginTop: "1rem", fontSize: "0.8rem", color: "#64748B" }}>
            Audit Output: <code>docs/data_audit_results.json</code>
          </div>
        </div>
      </div>
    </div>
  );
}
