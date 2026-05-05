/**
 * QualityScoreGauge — radial 0-100 indicator for AIM Quality Score.
 *
 * Color thresholds mirror backend gates:
 *   ≥85 green (passes hard gate)
 *   70-84 amber (revision zone)
 *   <70 red (reject zone)
 */
"use client";

import * as React from "react";

export interface QualityScoreGaugeProps {
  score: number | null | undefined;
  label?: string;
  size?: number;
}

export function QualityScoreGauge({ score, label = "AIM Quality", size = 120 }: QualityScoreGaugeProps) {
  const value = typeof score === "number" ? Math.max(0, Math.min(100, score)) : 0;
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - value / 100);
  const color =
    value >= 85 ? "#16a34a" : value >= 70 ? "#d97706" : "#dc2626";

  return (
    <div style={{ width: size }} className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="#e5e7eb"
          strokeWidth={8}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dashoffset 600ms ease, stroke 200ms" }}
        />
        <text
          x="50%"
          y="48%"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size / 4}
          fontWeight={700}
          fill={color}
        >
          {Math.round(value)}
        </text>
        <text
          x="50%"
          y="68%"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size / 12}
          fill="#6b7280"
        >
          / 100
        </text>
      </svg>
      <span className="text-xs text-gray-600">{label}</span>
    </div>
  );
}
