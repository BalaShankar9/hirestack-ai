"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";
import { DigitCounter } from "./digit-counter";

interface ScoreEntry {
  label: string;
  value: number;
}

interface ScoreGridProps {
  scores: ScoreEntry[];
  className?: string;
}

function barColor(score: number): string {
  if (score >= 90) return "bg-emerald-500";
  if (score >= 70) return "bg-primary";
  if (score >= 50) return "bg-amber-500";
  return "bg-rose-500";
}

export const ScoreGrid = memo(function ScoreGrid({ scores, className }: ScoreGridProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-x-6 gap-y-2", className)} role="status">
      {scores.map((s) => (
        <div key={s.label} className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-24 shrink-0 truncate">{s.label}</span>
          <DigitCounter value={s.value} suffix="%" className="text-sm w-10" />
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", barColor(s.value))}
              style={{ width: `${s.value}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
});
