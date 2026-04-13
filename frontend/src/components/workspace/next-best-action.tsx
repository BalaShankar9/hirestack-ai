"use client";

import { Zap, ArrowRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface NextBestActionProps {
  topFix?: string;
  /** Which tab to navigate to for the recommended action */
  targetTab?: string;
  onNavigate?: (tab: string) => void;
  /** Number of unsupported gaps — adds urgency context */
  gapCount?: number;
  /** Lowest scoring dimension name */
  weakestDimension?: string;
  weakestScore?: number;
}

/** Infer which tab the topFix likely relates to. */
function inferTargetTab(topFix: string): string {
  const lower = topFix.toLowerCase();
  if (lower.includes("keyword") || lower.includes("gap") || lower.includes("missing")) return "gaps";
  if (lower.includes("evidence") || lower.includes("proof") || lower.includes("portfolio")) return "portfolio";
  if (lower.includes("cv") || lower.includes("resume") || lower.includes("format")) return "cv";
  if (lower.includes("cover") || lower.includes("letter") || lower.includes("narrative")) return "cover";
  if (lower.includes("ats") || lower.includes("scan")) return "ats";
  if (lower.includes("learn") || lower.includes("skill") || lower.includes("course")) return "learning";
  if (lower.includes("benchmark") || lower.includes("rubric")) return "benchmark";
  return "gaps";
}

export function NextBestAction({
  topFix,
  targetTab,
  onNavigate,
  gapCount,
  weakestDimension,
  weakestScore,
}: NextBestActionProps) {
  if (!topFix) {
    return (
      <div className="rounded-xl border border-dashed border-primary/20 bg-primary/[0.02] p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 shrink-0">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">
              Generate modules to unlock your next best move
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Once AI analysis runs, you&apos;ll see the single highest-impact action to take next.
            </div>
          </div>
        </div>
      </div>
    );
  }

  const resolvedTab = targetTab || inferTargetTab(topFix);

  return (
    <div className="rounded-xl border border-primary/25 bg-gradient-to-r from-primary/[0.06] via-violet-500/[0.04] to-transparent p-4 shadow-soft-sm transition-all duration-300 hover:shadow-glow-sm glow-border-hover">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-white shrink-0">
          <Zap className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary">
              Next best move
            </span>
          </div>
          <div className="mt-1 text-sm font-semibold text-foreground leading-snug">
            {topFix}
          </div>
          {(gapCount !== undefined && gapCount > 0) || (weakestScore !== undefined && weakestScore < 50) ? (
            <div className="mt-1.5 text-xs text-muted-foreground leading-snug">
              {weakestDimension && weakestScore !== undefined
                ? `${weakestDimension} is at ${weakestScore}% — this action targets the biggest drag on your score.`
                : gapCount
                  ? `${gapCount} gaps remain unsupported. Fixing this will have the highest impact.`
                  : null}
            </div>
          ) : null}
          <div className="mt-3">
            <Button
              size="sm"
              className="gap-2 rounded-xl"
              onClick={() => onNavigate?.(resolvedTab)}
            >
              Take action
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
