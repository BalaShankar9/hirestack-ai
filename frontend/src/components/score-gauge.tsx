"use client"

import { cn } from "@/lib/utils"

interface ScoreGaugeProps {
  score: number
  size?: "sm" | "md" | "lg"
  showLabel?: boolean
  label?: string
  className?: string
}

export function ScoreGauge({
  score,
  size = "md",
  showLabel = true,
  label = "Compatibility",
  className,
}: ScoreGaugeProps) {
  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-500"
    if (score >= 60) return "text-blue-500"
    if (score >= 40) return "text-yellow-500"
    return "text-red-500"
  }

  const getStrokeColor = (score: number) => {
    if (score >= 80) return "stroke-green-500"
    if (score >= 60) return "stroke-blue-500"
    if (score >= 40) return "stroke-yellow-500"
    return "stroke-red-500"
  }

  const getScoreLabel = (score: number) => {
    if (score >= 80) return "Excellent"
    if (score >= 60) return "Good"
    if (score >= 40) return "Fair"
    return "Needs Work"
  }

  const sizes = {
    sm: { width: 80, strokeWidth: 6, fontSize: "text-lg" },
    md: { width: 120, strokeWidth: 8, fontSize: "text-2xl" },
    lg: { width: 160, strokeWidth: 10, fontSize: "text-4xl" },
  }

  const { width, strokeWidth, fontSize } = sizes[size]
  const radius = (width - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (score / 100) * circumference

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <div className="relative" style={{ width, height: width }}>
        <svg
          className="transform -rotate-90"
          width={width}
          height={width}
        >
          {/* Background circle */}
          <circle
            className="stroke-muted"
            fill="none"
            strokeWidth={strokeWidth}
            r={radius}
            cx={width / 2}
            cy={width / 2}
          />
          {/* Progress circle */}
          <circle
            className={cn("transition-all duration-1000", getStrokeColor(score))}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            r={radius}
            cx={width / 2}
            cy={width / 2}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("font-bold", fontSize, getScoreColor(score))}>
            {score}%
          </span>
        </div>
      </div>
      {showLabel && (
        <div className="mt-2 text-center">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className={cn("font-medium", getScoreColor(score))}>
            {getScoreLabel(score)}
          </p>
        </div>
      )}
    </div>
  )
}
