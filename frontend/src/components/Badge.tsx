import React from "react";

interface BadgeProps {
  label: string | number;
  variant?: "success" | "warning" | "danger" | "info" | "neutral" | "purple";
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({ label, variant = "neutral", size = "sm" }) => {
  const getStyles = () => {
    switch (variant) {
      case "success":
        return { background: "rgba(16, 185, 129, 0.15)", color: "#34D399", border: "1px solid rgba(16, 185, 129, 0.3)" };
      case "warning":
        return { background: "rgba(245, 158, 11, 0.15)", color: "#FBBF24", border: "1px solid rgba(245, 158, 11, 0.3)" };
      case "danger":
        return { background: "rgba(239, 68, 68, 0.15)", color: "#F87171", border: "1px solid rgba(239, 68, 68, 0.3)" };
      case "info":
        return { background: "rgba(56, 189, 248, 0.15)", color: "#38BDF8", border: "1px solid rgba(56, 189, 248, 0.3)" };
      case "purple":
        return { background: "rgba(168, 85, 247, 0.15)", color: "#C084FC", border: "1px solid rgba(168, 85, 247, 0.3)" };
      default:
        return { background: "rgba(148, 163, 184, 0.12)", color: "#CBD5E1", border: "1px solid rgba(148, 163, 184, 0.25)" };
    }
  };

  const style = getStyles();
  const padding = size === "sm" ? "2px 8px" : "4px 12px";
  const fontSize = size === "sm" ? "0.72rem" : "0.85rem";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        borderRadius: "9999px",
        fontWeight: 600,
        letterSpacing: "0.02em",
        padding,
        fontSize,
        ...style,
      }}
    >
      {label}
    </span>
  );
};
