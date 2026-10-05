import React from "react";

export function Badge({ label, color, size }) {
  return (
    <span className={`badge badge-${color} badge-${size}`}>{label}</span>
  );
}

Badge.defaultProps = {
  color: "grey",
  size: "md",
};
