"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { HelpCircle, X, ChevronDown } from "lucide-react";

interface ScoreExplanationProps {
  /** The score value (0-100) */
  score: number;
  /** Short label for the score */
  label: string;
  /** Detailed explanation of how the score works */
  methodology: string;
  /** Factors that contributed to the score */
  factors?: { label: string; impact: "positive" | "negative" | "neutral"; detail?: string }[];
  /** What would improve this score */
  improvements?: string[];
  className?: string;
}

/**
 * Explainable score component.
 * Shows a score with "How this works" expandable section
 * to build trust and transparency.
 */
export function ScoreExplanation({
  score,
  label,
  methodology,
  factors,
  improvements,
  className,
}: ScoreExplanationProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn("rounded-xl border bg-card", className)}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 p-3 text-left hover:bg-muted/30 transition-all rounded-xl"
      >
        <HelpCircle className="h-4 w-4 text-muted-foreground/60 shrink-0" />
        <span className="text-xs text-muted-foreground flex-1">
          How {label.toLowerCase()} score works
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-muted-foreground/50 transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && (
        <div className="border-t px-4 py-3 space-y-3">
          <p className="text-xs text-muted-foreground leading-relaxed">
            {methodology}
          </p>

          {factors && factors.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-foreground">Contributing factors:</p>
              {factors.map((f, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <div
                    className={cn(
                      "mt-1 h-1.5 w-1.5 rounded-full shrink-0",
                      f.impact === "positive" && "bg-emerald-500",
                      f.impact === "negative" && "bg-rose-500",
                      f.impact === "neutral" && "bg-muted-foreground/40"
                    )}
                  />
                  <div>
                    <span className="text-foreground">{f.label}</span>
                    {f.detail && (
                      <span className="text-muted-foreground"> — {f.detail}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {improvements && improvements.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-foreground">To improve this score:</p>
              <ul className="space-y-1">
                {improvements.map((imp, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <span className="text-primary font-bold">→</span>
                    {imp}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
