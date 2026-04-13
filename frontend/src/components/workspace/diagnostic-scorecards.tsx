"use client";

import { Target, ShieldCheck, ScanEye, Award, ArrowRight, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { ApplicationDoc, GapsModule, BenchmarkModule } from "@/lib/firestore";

type Scores = NonNullable<ApplicationDoc["scores"]>;

function metricColor(score: number) {
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-blue-600";
  if (score >= 40) return "text-amber-600";
  return "text-rose-600";
}

function meterColor(score: number) {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-blue-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-rose-500";
}

interface DiagnosticCard {
  icon: React.ReactNode;
  label: string;
  score: number;
  description: string;
  drags: string[];
  improves: string;
  targetTab: string;
}

function buildDiagnostics(
  scores: Scores,
  gaps?: GapsModule,
  benchmark?: BenchmarkModule,
): DiagnosticCard[] {
  const missingCount = gaps?.missingKeywords?.length ?? 0;
  const strengthCount = gaps?.strengths?.length ?? 0;
  const recCount = gaps?.recommendations?.length ?? 0;

  return [
    {
      icon: <Target className="h-4 w-4" />,
      label: "Match",
      score: scores.match ?? 0,
      description: "How well your profile keywords align with the job description.",
      drags: [
        ...(missingCount > 0 ? [`${missingCount} keywords missing from your documents`] : []),
        ...(strengthCount === 0 ? ["No matched keywords detected yet"] : []),
      ],
      improves: "Add missing keywords to your CV and cover letter with evidence.",
      targetTab: "gaps",
    },
    {
      icon: <ShieldCheck className="h-4 w-4" />,
      label: "ATS Readiness",
      score: scores.atsReadiness ?? 0,
      description: "Keyword coverage and structural signals for ATS parsing.",
      drags: [
        ...(missingCount > 3 ? [`${missingCount} critical keywords not found by ATS`] : []),
        ...((scores.atsReadiness ?? 0) < 50 ? ["Document structure may not parse correctly"] : []),
      ],
      improves: "Run ATS scan and address flagged formatting and keyword issues.",
      targetTab: "ats",
    },
    {
      icon: <ScanEye className="h-4 w-4" />,
      label: "6-Second Scan",
      score: scores.recruiterScan ?? 0,
      description: "How clear and compelling the top third of your CV appears.",
      drags: [
        ...((scores.recruiterScan ?? 0) < 50 ? ["Top-third clarity needs improvement"] : []),
        ...(recCount > 0 ? [`${recCount} recommendations waiting to be addressed`] : []),
      ],
      improves: "Lead with strongest outcomes and keep the header section tight.",
      targetTab: "cv",
    },
    {
      icon: <Award className="h-4 w-4" />,
      label: "Evidence Strength",
      score: scores.evidenceStrength ?? 0,
      description: "Proof items linked to claims across your application.",
      drags: [
        ...((scores.evidenceStrength ?? 0) < 30 ? ["Very few evidence items linked to claims"] : []),
        ...((scores.evidenceStrength ?? 0) === 0 ? ["No verified evidence linked yet — this limits trust"] : []),
      ],
      improves: "Link portfolio projects, certs, and publications to back up claims.",
      targetTab: "portfolio",
    },
  ];
}

export function DiagnosticScorecards({
  scores,
  gaps,
  benchmark,
  onNavigate,
}: {
  scores?: Scores;
  gaps?: GapsModule;
  benchmark?: BenchmarkModule;
  onNavigate?: (tab: string) => void;
}) {
  const sc = scores ?? {};
  const cards = buildDiagnostics(sc, gaps, benchmark);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {cards.map((card) => (
        <div
          key={card.label}
          className="surface-premium rounded-2xl p-4 transition-all duration-300 hover:shadow-soft-lg hover:-translate-y-0.5 card-spotlight"
        >
          {/* Header: icon + label + score */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <div className="text-muted-foreground">{card.icon}</div>
              <span className="text-xs font-medium text-muted-foreground">{card.label}</span>
            </div>
            <span className={cn("text-lg font-bold tabular-nums", metricColor(card.score))}>
              {card.score > 0 ? `${card.score}%` : "—"}
            </span>
          </div>

          {/* Meter */}
          <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", meterColor(card.score))}
              style={{ width: `${card.score}%` }}
            />
          </div>

          {/* Description */}
          <p className="mt-2.5 text-[11px] text-muted-foreground leading-snug">
            {card.description}
          </p>

          {/* Drags */}
          {card.drags.length > 0 && card.score > 0 && (
            <div className="mt-2.5 space-y-1">
              {card.drags.map((d, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                  <span className="leading-snug">{d}</span>
                </div>
              ))}
            </div>
          )}

          {/* Improve action */}
          {card.score > 0 && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground leading-snug flex-1">
                {card.improves}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1 text-xs rounded-lg shrink-0 h-7 px-2"
                onClick={() => onNavigate?.(card.targetTab)}
              >
                Fix
                <ArrowRight className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
