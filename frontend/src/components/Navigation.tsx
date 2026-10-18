import React from "react";
import {
  LayoutDashboard,
  Table,
  LineChart,
  Boxes,
  AlertTriangle,
  Award,
  Database,
  RefreshCw,
} from "lucide-react";

export type ScreenId =
  | "overview"
  | "forecasting"
  | "details"
  | "inventory"
  | "low_confidence"
  | "evaluation"
  | "data_quality";

interface NavigationProps {
  activeScreen: ScreenId;
  onScreenChange: (screen: ScreenId) => void;
  selectedSKUId: string | null;
  runId: string;
  isBackendHealthy: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeScreen,
  onScreenChange,
  selectedSKUId,
  runId,
  isBackendHealthy,
  onRefresh,
  isRefreshing,
}) => {
  const navItems: Array<{ id: ScreenId; label: string; icon: React.ReactNode }> = [
    { id: "overview", label: "Overview", icon: <LayoutDashboard size={16} /> },
    { id: "forecasting", label: "SKU Forecasts", icon: <Table size={16} /> },
    {
      id: "details",
      label: selectedSKUId ? `Detail: ${selectedSKUId}` : "SKU Details",
      icon: <LineChart size={16} />,
    },
    { id: "inventory", label: "Inventory Planning", icon: <Boxes size={16} /> },
    { id: "low_confidence", label: "Low-Confidence Review", icon: <AlertTriangle size={16} /> },
    { id: "evaluation", label: "Model Evaluation", icon: <Award size={16} /> },
    { id: "data_quality", label: "Data Quality & Lineage", icon: <Database size={16} /> },
  ];

  return (
    <header
      style={{
        background: "#0B0F17",
        borderBottom: "1px solid #1E293B",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      {/* Top Bar: Brand, Status, Actions */}
      <div
        style={{
          padding: "0.85rem 1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #131B2E",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              background: "linear-gradient(135deg, #6366F1, #38BDF8)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: "1rem",
              color: "#FFFFFF",
              letterSpacing: "-0.05em",
            }}
          >
            R4
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "1.05rem", fontWeight: 700, color: "#F8FAFC" }}>
                R4 New Product Demand Forecasting
              </span>
              <span
                style={{
                  fontSize: "0.7rem",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "#1E293B",
                  color: "#94A3B8",
                  fontWeight: 600,
                }}
              >
                PROD v0.9.0
              </span>
            </div>
            <p style={{ margin: "1px 0 0 0", fontSize: "0.78rem", color: "#64748B" }}>
              Cold-Start 8-Week Horizon Forecasting & Newsvendor Inventory Optimization
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {/* Run ID pill */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
              background: "#111827",
              border: "1px solid #1F2937",
              padding: "0.3rem 0.75rem",
              borderRadius: "6px",
              fontSize: "0.78rem",
            }}
          >
            <span style={{ color: "#64748B" }}>Active Run:</span>
            <strong style={{ color: "#38BDF8", fontFamily: "'Geist Mono', monospace" }}>{runId}</strong>
          </div>

          {/* Backend Health Badge */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
              background: isBackendHealthy ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
              border: `1px solid ${isBackendHealthy ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
              padding: "0.3rem 0.75rem",
              borderRadius: "6px",
              fontSize: "0.78rem",
              color: isBackendHealthy ? "#34D399" : "#F87171",
              fontWeight: 600,
            }}
          >
            <span
              style={{
                width: "7px",
                height: "7px",
                borderRadius: "50%",
                background: isBackendHealthy ? "#10B981" : "#EF4444",
                boxShadow: isBackendHealthy ? "0 0 8px #10B981" : "none",
              }}
            ></span>
            <span>FastAPI: {isBackendHealthy ? "Connected" : "Offline"}</span>
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            style={{
              background: "#1E293B",
              border: "1px solid #334155",
              color: "#CBD5E1",
              borderRadius: "6px",
              padding: "0.35rem 0.75rem",
              fontSize: "0.78rem",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
              cursor: isRefreshing ? "not-allowed" : "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <RefreshCw size={13} style={{ animation: isRefreshing ? "spin 1s linear infinite" : "none" }} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Tabs Navigation */}
      <nav
        style={{
          display: "flex",
          gap: "0.5rem",
          padding: "0.4rem 1.5rem",
          overflowX: "auto",
        }}
      >
        {navItems.map((item) => {
          const isActive = activeScreen === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onScreenChange(item.id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.45rem 0.85rem",
                borderRadius: "6px",
                fontSize: "0.82rem",
                fontWeight: isActive ? 600 : 500,
                color: isActive ? "#38BDF8" : "#94A3B8",
                background: isActive ? "rgba(56, 189, 248, 0.1)" : "transparent",
                border: isActive ? "1px solid rgba(56, 189, 248, 0.3)" : "1px solid transparent",
                cursor: "pointer",
                whiteSpace: "nowrap",
                transition: "all 0.15s ease",
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
};
