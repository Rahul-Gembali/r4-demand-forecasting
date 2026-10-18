import React from "react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  badge?: {
    text: string;
    variant: "success" | "warning" | "danger" | "info" | "neutral" | "purple";
  };
  icon?: React.ReactNode;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  badge,
  icon,
  trend,
}) => {
  return (
    <div
      style={{
        background: "#111827",
        border: "1px solid #1F2937",
        borderRadius: "12px",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.2)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "0.8rem", color: "#94A3B8", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
          {title}
        </span>
        {icon && <div style={{ color: "#64748B" }}>{icon}</div>}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginTop: "0.25rem" }}>
        <span style={{ fontSize: "1.75rem", fontWeight: 700, color: "#F8FAFC", fontFamily: "'Geist Mono', monospace" }}>
          {value}
        </span>
        {badge && (
          <span
            style={{
              fontSize: "0.75rem",
              padding: "2px 8px",
              borderRadius: "9999px",
              fontWeight: 600,
              background:
                badge.variant === "success"
                  ? "rgba(16, 185, 129, 0.15)"
                  : badge.variant === "danger"
                  ? "rgba(239, 68, 68, 0.15)"
                  : badge.variant === "warning"
                  ? "rgba(245, 158, 11, 0.15)"
                  : badge.variant === "purple"
                  ? "rgba(168, 85, 247, 0.15)"
                  : "rgba(56, 189, 248, 0.15)",
              color:
                badge.variant === "success"
                  ? "#34D399"
                  : badge.variant === "danger"
                  ? "#F87171"
                  : badge.variant === "warning"
                  ? "#FBBF24"
                  : badge.variant === "purple"
                  ? "#C084FC"
                  : "#38BDF8",
            }}
          >
            {badge.text}
          </span>
        )}
      </div>

      {(subtitle || trend) && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", color: "#64748B" }}>
          {trend && (
            <span style={{ color: trend.isPositive ? "#10B981" : "#F87171", fontWeight: 600 }}>
              {trend.value}
            </span>
          )}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
