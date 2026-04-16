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
  Code2,
  Globe,
  Users,
  Briefcase,
  Key,
  TrendingUp,
  MessageSquare,
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

  // ── Rich company intel display ────────────────────────────────
  const intel = app.companyIntel;
  if (intel && typeof intel === "object" && Object.keys(intel).length > 0) {
    const confidence = intel.confidence || "unknown";
    const dataSources: string[] = Array.isArray(intel.data_sources) ? intel.data_sources : [];
    const sourceCount = dataSources.length;

    // Overall intel confidence
    const confColor =
      confidence === "high"
        ? "text-emerald-600 bg-emerald-500/10"
        : confidence === "medium"
          ? "text-teal-600 bg-teal-500/10"
          : "text-amber-600 bg-amber-500/10";
    items.push({
      icon: <Building2 className="h-3.5 w-3.5" />,
      label: `Company intel: ${confidence} confidence from ${sourceCount} source${sourceCount !== 1 ? "s" : ""}`,
      color: confColor,
    });

    // Tech stack
    const techData = intel.tech_and_engineering;
    if (techData && typeof techData === "object") {
      const techStack: string[] = Array.isArray(techData.tech_stack)
        ? techData.tech_stack
        : [];
      const jdTech = techData.jd_tech_stack;
      let allTech = [...techStack];
      if (jdTech && typeof jdTech === "object" && !Array.isArray(jdTech)) {
        for (const catItems of Object.values(jdTech)) {
          if (Array.isArray(catItems)) allTech.push(...(catItems as string[]));
        }
      }
      allTech = [...new Set(allTech)];
      if (allTech.length > 0) {
        items.push({
          icon: <Code2 className="h-3.5 w-3.5" />,
          label: `Tech stack: ${allTech.slice(0, 8).join(", ")}${allTech.length > 8 ? ` +${allTech.length - 8} more` : ""}`,
          color: "text-cyan-600 bg-cyan-500/10",
        });
      }

      // GitHub presence
      const gh = techData.github_stats;
      if (gh && typeof gh === "object" && gh.org_name) {
        const repoCount = gh.public_repos ?? 0;
        const activity = gh.activity_level ?? "Unknown";
        items.push({
          icon: <Globe className="h-3.5 w-3.5" />,
          label: `GitHub: ${gh.org_name} — ${repoCount} repos, ${activity} activity`,
          color: "text-gray-600 bg-gray-500/10",
        });
      }
    }

    // Hiring intel
    const hiringData = intel.hiring_intelligence;
    if (hiringData && typeof hiringData === "object") {
      const mustHave: string[] = Array.isArray(hiringData.must_have_skills)
        ? hiringData.must_have_skills
        : [];
      if (mustHave.length > 0) {
        items.push({
          icon: <Key className="h-3.5 w-3.5" />,
          label: `Must-have: ${mustHave.slice(0, 5).join(", ")}${mustHave.length > 5 ? ` +${mustHave.length - 5}` : ""}`,
          color: "text-red-600 bg-red-500/10",
        });
      }
      if (hiringData.ats_platform) {
        items.push({
          icon: <Briefcase className="h-3.5 w-3.5" />,
          label: `ATS platform: ${hiringData.ats_platform}`,
          color: "text-indigo-600 bg-indigo-500/10",
        });
      }
    }

    // Culture
    const cultureData = intel.culture_and_values;
    if (cultureData && typeof cultureData === "object") {
      const values: string[] = Array.isArray(cultureData.core_values) ? cultureData.core_values : [];
      if (values.length > 0) {
        items.push({
          icon: <Users className="h-3.5 w-3.5" />,
          label: `Values: ${values.slice(0, 4).join(", ")}`,
          color: "text-purple-600 bg-purple-500/10",
        });
      }
      const workStyle = cultureData.work_style;
      if (typeof workStyle === "string" && workStyle && workStyle.toLowerCase() !== "unknown") {
        items.push({
          icon: <Building2 className="h-3.5 w-3.5" />,
          label: `Work style: ${workStyle}`,
          color: "text-teal-600 bg-teal-500/10",
        });
      }
    }

    // Application strategy highlights
    const strategy = intel.application_strategy;
    if (strategy && typeof strategy === "object") {
      const keywords: string[] = Array.isArray(strategy.keywords_to_use) ? strategy.keywords_to_use : [];
      if (keywords.length > 0) {
        items.push({
          icon: <TrendingUp className="h-3.5 w-3.5" />,
          label: `Strategic keywords: ${keywords.slice(0, 6).join(", ")}${keywords.length > 6 ? ` +${keywords.length - 6}` : ""}`,
          color: "text-blue-600 bg-blue-500/10",
        });
      }
      const hooks: string[] = Array.isArray(strategy.cover_letter_hooks) ? strategy.cover_letter_hooks : [];
      if (hooks.length > 0) {
        items.push({
          icon: <MessageSquare className="h-3.5 w-3.5" />,
          label: `${hooks.length} cover letter opening hook${hooks.length !== 1 ? "s" : ""} generated`,
          color: "text-violet-600 bg-violet-500/10",
        });
      }
      const prep: string[] = Array.isArray(strategy.interview_prep_topics) ? strategy.interview_prep_topics : [];
      if (prep.length > 0) {
        items.push({
          icon: <Target className="h-3.5 w-3.5" />,
          label: `${prep.length} interview prep topic${prep.length !== 1 ? "s" : ""} identified`,
          color: "text-orange-600 bg-orange-500/10",
        });
      }
    }

    // Red flags
    const redFlags: string[] = Array.isArray(cultureData?.red_flags)
      ? cultureData.red_flags
      : [];
    if (redFlags.length > 0) {
      items.push({
        icon: <AlertTriangle className="h-3.5 w-3.5" />,
        label: `${redFlags.length} potential concern${redFlags.length !== 1 ? "s" : ""} flagged`,
        color: "text-red-600 bg-red-500/10",
      });
    }
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
