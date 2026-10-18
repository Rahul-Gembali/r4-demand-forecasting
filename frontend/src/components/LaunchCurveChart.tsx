import React, { useState } from "react";
import { AnalogueMatchDetail, WeeklyForecastItem } from "../types/api";

interface LaunchCurveChartProps {
  forecasts: WeeklyForecastItem[];
  analogues?: AnalogueMatchDetail[];
  title?: string;
  height?: number;
}

export const LaunchCurveChart: React.FC<LaunchCurveChartProps> = ({
  forecasts,
  analogues = [],
  title = "8-Week Launch Curve & Conformal Uncertainty Bands",
  height = 320,
}) => {
  const [hoveredWeek, setHoveredWeek] = useState<number | null>(null);

  if (!forecasts || forecasts.length === 0) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#111827",
          borderRadius: "12px",
          color: "#64748B",
        }}
      >
        No launch curve data available.
      </div>
    );
  }

  // Margins & Dimensions
  const width = 760;
  const padding = { top: 30, right: 30, bottom: 45, left: 55 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Compute Scales
  const maxForecastVal = Math.max(
    ...forecasts.map((f) => Math.max(f.predicted_sales, f.upper_bound_90 || 0, f.upper_bound_80 || 0)),
    ...analogues.flatMap((a) => (a.observed_curve ? a.observed_curve : [0]))
  );

  const maxY = Math.ceil((maxForecastVal * 1.15) / 10) * 10 || 100;
  const minY = 0;

  const getX = (week: number) => padding.left + ((week - 1) / (forecasts.length - 1)) * chartWidth;
  const getY = (val: number) => padding.top + chartHeight - ((val - minY) / (maxY - minY)) * chartHeight;

  // Construct SVG paths
  const pointCoords = forecasts.map((f) => ({ x: getX(f.horizon_week), y: getY(f.predicted_sales) }));

  const linePath = pointCoords.reduce(
    (acc, curr, idx) => (idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`),
    ""
  );

  // 90% Uncertainty Area Path
  const upper90Coords = forecasts.map((f) => ({
    x: getX(f.horizon_week),
    y: getY(f.upper_bound_90 ?? f.predicted_sales * 1.3),
  }));
  const lower90Coords = [...forecasts]
    .reverse()
    .map((f) => ({
      x: getX(f.horizon_week),
      y: getY(Math.max(0, f.lower_bound_90 ?? f.predicted_sales * 0.7)),
    }));

  const area90Path =
    upper90Coords.reduce((acc, curr, idx) => (idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`), "") +
    lower90Coords.reduce((acc, curr) => `${acc} L ${curr.x} ${curr.y}`, "") +
    " Z";

  // 80% Uncertainty Area Path
  const upper80Coords = forecasts.map((f) => ({
    x: getX(f.horizon_week),
    y: getY(f.upper_bound_80 ?? f.predicted_sales * 1.2),
  }));
  const lower80Coords = [...forecasts]
    .reverse()
    .map((f) => ({
      x: getX(f.horizon_week),
      y: getY(Math.max(0, f.lower_bound_80 ?? f.predicted_sales * 0.8)),
    }));

  const area80Path =
    upper80Coords.reduce((acc, curr, idx) => (idx === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`), "") +
    lower80Coords.reduce((acc, curr) => `${acc} L ${curr.x} ${curr.y}`, "") +
    " Z";

  // Y-axis ticks
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map((t) => Math.round(minY + t * (maxY - minY)));

  const hoveredItem = hoveredWeek !== null ? forecasts.find((f) => f.horizon_week === hoveredWeek) : null;

  return (
    <div
      style={{
        background: "#111827",
        border: "1px solid #1F2937",
        borderRadius: "12px",
        padding: "1.25rem",
        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.2)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
        <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "#F8FAFC", margin: 0 }}>{title}</h3>
        {/* Legend */}
        <div style={{ display: "flex", gap: "1rem", alignItems: "center", fontSize: "0.75rem", color: "#94A3B8" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "12px", height: "3px", background: "#38BDF8", borderRadius: "2px" }}></span>
            <span>Point Forecast (Median)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "10px", height: "10px", background: "rgba(56, 189, 248, 0.35)", borderRadius: "2px" }}></span>
            <span>80% Interval</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{ width: "10px", height: "10px", background: "rgba(99, 102, 241, 0.2)", borderRadius: "2px" }}></span>
            <span>90% Interval</span>
          </div>
          {analogues.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
              <span style={{ width: "12px", height: "2px", borderTop: "2px dashed #F59E0B" }}></span>
              <span>Top Analogue</span>
            </div>
          )}
        </div>
      </div>

      <div style={{ position: "relative", width: "100%", overflowX: "auto" }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
          {/* Grid lines */}
          {yTicks.map((val) => (
            <g key={val}>
              <line
                x1={padding.left}
                y1={getY(val)}
                x2={width - padding.right}
                y2={getY(val)}
                stroke="#1F2937"
                strokeDasharray="4 4"
              />
              <text
                x={padding.left - 10}
                y={getY(val) + 4}
                textAnchor="end"
                fontSize="11"
                fill="#64748B"
                fontFamily="'Geist Mono', monospace"
              >
                {val}
              </text>
            </g>
          ))}

          {/* X Axis ticks */}
          {forecasts.map((f) => (
            <g key={f.horizon_week}>
              <text
                x={getX(f.horizon_week)}
                y={height - padding.bottom + 20}
                textAnchor="middle"
                fontSize="11"
                fill={hoveredWeek === f.horizon_week ? "#38BDF8" : "#94A3B8"}
                fontWeight={hoveredWeek === f.horizon_week ? "bold" : "normal"}
              >
                W{f.horizon_week}
              </text>
              <line
                x1={getX(f.horizon_week)}
                y1={padding.top}
                x2={getX(f.horizon_week)}
                y2={height - padding.bottom}
                stroke={hoveredWeek === f.horizon_week ? "#38BDF8" : "transparent"}
                strokeWidth={hoveredWeek === f.horizon_week ? "1.5" : "0"}
                strokeDasharray="3 3"
                opacity="0.6"
              />
            </g>
          ))}

          {/* 90% Uncertainty Shaded Area */}
          <path d={area90Path} fill="rgba(99, 102, 241, 0.18)" />

          {/* 80% Uncertainty Shaded Area */}
          <path d={area80Path} fill="rgba(56, 189, 248, 0.25)" />

          {/* Top-1 Analogue Observed Launch Curve */}
          {analogues.length > 0 && analogues[0].observed_curve && (
            <path
              d={analogues[0].observed_curve.slice(0, 8).reduce((acc, val, idx) => {
                const x = getX(idx + 1);
                const y = getY(val);
                return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
              }, "")}
              fill="none"
              stroke="#F59E0B"
              strokeWidth="1.8"
              strokeDasharray="5 3"
              opacity="0.8"
            />
          )}

          {/* Point Forecast Line */}
          <path d={linePath} fill="none" stroke="#38BDF8" strokeWidth="2.5" />

          {/* Interactive Data Points */}
          {forecasts.map((f) => {
            const x = getX(f.horizon_week);
            const y = getY(f.predicted_sales);
            const isHovered = hoveredWeek === f.horizon_week;
            return (
              <g
                key={f.horizon_week}
                onMouseEnter={() => setHoveredWeek(f.horizon_week)}
                onMouseLeave={() => setHoveredWeek(null)}
                style={{ cursor: "pointer" }}
              >
                {/* Hit area */}
                <circle cx={x} cy={y} r="18" fill="transparent" />
                {/* Outer halo on hover */}
                {isHovered && <circle cx={x} cy={y} r="8" fill="rgba(56, 189, 248, 0.3)" />}
                {/* Core point */}
                <circle
                  cx={x}
                  cy={y}
                  r={isHovered ? 5.5 : 4}
                  fill="#0B0F17"
                  stroke="#38BDF8"
                  strokeWidth="2.5"
                />
              </g>
            );
          })}
        </svg>

        {/* Floating Tooltip */}
        {hoveredItem && (
          <div
            style={{
              position: "absolute",
              top: "12px",
              right: "20px",
              background: "#030712",
              border: "1px solid #38BDF8",
              borderRadius: "8px",
              padding: "0.5rem 0.85rem",
              boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
              fontSize: "0.8rem",
              color: "#F8FAFC",
              pointerEvents: "none",
            }}
          >
            <div style={{ fontWeight: 700, color: "#38BDF8", marginBottom: "0.25rem" }}>
              Launch Week {hoveredItem.horizon_week}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <span style={{ color: "#94A3B8" }}>Point Forecast:</span>
              <strong style={{ fontFamily: "'Geist Mono', monospace" }}>
                {hoveredItem.predicted_sales.toFixed(1)} units
              </strong>
            </div>
            {hoveredItem.lower_bound_80 !== null && (
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                <span style={{ color: "#94A3B8" }}>80% Interval:</span>
                <span style={{ fontFamily: "'Geist Mono', monospace", color: "#67E8F9" }}>
                  [{hoveredItem.lower_bound_80?.toFixed(1)} – {hoveredItem.upper_bound_80?.toFixed(1)}]
                </span>
              </div>
            )}
            {hoveredItem.lower_bound_90 !== null && (
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                <span style={{ color: "#94A3B8" }}>90% Interval:</span>
                <span style={{ fontFamily: "'Geist Mono', monospace", color: "#A5B4FC" }}>
                  [{hoveredItem.lower_bound_90?.toFixed(1)} – {hoveredItem.upper_bound_90?.toFixed(1)}]
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
