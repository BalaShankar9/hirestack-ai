"use client";

import { useMemo } from "react";
import {
  Search,
  AlertTriangle,
  Lightbulb,
  Building2,
  Shield,
  FileText,
  CheckCircle2,
  Target,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApplicationDoc, GapsModule, BenchmarkModule } from "@/lib/firestore";

interface InsightItem {
  icon: React.ReactNode;
  label: string;
  color: string;
}

function buildInsights(
  app: ApplicationDoc,
  keywordCount: number,
  missingCount: number,
  evidenceCount: number,
): InsightItem[] {
  const items: InsightItem[] = [];

  // Keywords extracted
  if (keywordCount > 0) {
    items.push({
      icon: <Search className="h-3.5 w-3.5" />,
      label: `${keywordCount} target keywords extracted from the job description`,
      color: "text-blue-600 bg-blue-500/10",
    });
  }

  // Missing keywords / gaps
  if (missingCount > 0) {
    items.push({
      icon: <AlertTriangle className="h-3.5 w-3.5" />,
      label: `${missingCount} keywords currently unsupported in your documents`,
      color: "text-amber-600 bg-amber-500/10",
    });
  }

  // Strengths
  const strengthCount = app.gaps?.strengths?.length ?? 0;
  if (strengthCount > 0) {
    items.push({
      icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      label: `${strengthCount} keywords already matched — strong foundation`,
      color: "text-emerald-600 bg-emerald-500/10",
    });
  }

  // Recommendations from gaps
  const recs = app.gaps?.recommendations ?? [];
  if (recs.length > 0) {
    items.push({
      icon: <Lightbulb className="h-3.5 w-3.5" />,
      label: `${recs.length} improvement recommendations generated`,
      color: "text-violet-600 bg-violet-500/10",
    });
  }

  // Benchmark dimensions
  const dims = app.benchmark?.dimensions?.length ?? 0;
  if (dims > 0) {
    items.push({
      icon: <Target className="h-3.5 w-3.5" />,
      label: `Ideal candidate profiled across ${dims} dimensions`,
      color: "text-blue-600 bg-blue-500/10",
    });
  }

  // Company intel
  const intel = app.companyIntel;
  if (intel && Object.keys(intel).length > 0) {
    const confidence = intel.confidence || "unknown";
    items.push({
      icon: <Building2 className="h-3.5 w-3.5" />,
      label: `Company intelligence gathered (${confidence} confidence)`,
      color: "text-teal-600 bg-teal-500/10",
    });
  }

  // Evidence
  if (evidenceCount > 0) {
    items.push({
      icon: <Shield className="h-3.5 w-3.5" />,
      label: `${evidenceCount} evidence items available for linking`,
      color: "text-emerald-600 bg-emerald-500/10",
    });
  } else {
    items.push({
      icon: <Shield className="h-3.5 w-3.5" />,
      label: "No evidence linked yet — this limits proof strength",
      color: "text-amber-600 bg-amber-500/10",
    });
  }

  // Validation
  if (app.validation && Object.keys(app.validation).length > 0) {
    items.push({
      icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      label: "Quality validation has been run on generated documents",
      color: "text-emerald-600 bg-emerald-500/10",
    });
  }

  // Discovered documents
  const discovered = app.discoveredDocuments?.length ?? 0;
  if (discovered > 0) {
    items.push({
      icon: <FileText className="h-3.5 w-3.5" />,
      label: `${discovered} document type${discovered > 1 ? "s" : ""} recommended by AI planner`,
      color: "text-blue-600 bg-blue-500/10",
    });
  }

  return items;
}

export function IntelligencePanel({
  app,
  keywordCount,
  missingCount,
  evidenceCount,
}: {
  app: ApplicationDoc;
  keywordCount: number;
  missingCount: number;
  evidenceCount: number;
}) {
  const insights = useMemo(
    () => buildInsights(app, keywordCount, missingCount, evidenceCount),
    [app, keywordCount, missingCount, evidenceCount],
  );

  if (insights.length === 0) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 p-4 text-center">
        <Sparkles className="h-6 w-6 text-muted-foreground/30 mx-auto mb-2" />
        <p className="text-xs text-muted-foreground">
          Intelligence findings will appear here once modules are generated.
        </p>
      </div>
    );
  }

  return (
    <div className="surface-premium rounded-2xl p-4 card-spotlight">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
          <Search className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="text-sm font-semibold">Live Intelligence</div>
        <span className="text-[10px] text-muted-foreground">
          {insights.length} finding{insights.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-1.5 max-h-[260px] overflow-y-auto">
        {insights.map((item, idx) => (
          <div
            key={idx}
            className="flex items-start gap-2.5 rounded-lg px-2.5 py-2 transition-colors hover:bg-muted/40"
            style={{ animationDelay: `${idx * 60}ms` }}
          >
            <div className={cn("mt-0.5 flex h-6 w-6 items-center justify-center rounded-md shrink-0", item.color)}>
              {item.icon}
            </div>
            <span className="text-xs text-foreground/90 leading-snug">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
