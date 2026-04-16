"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import { useApplications } from "@/lib/firestore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  Target, AlertTriangle, TrendingUp, BookOpen, ArrowRight,
  RefreshCw, Layers, ChevronDown, ChevronUp, ExternalLink, Zap,
  CheckCircle, XCircle, Minus,
} from "lucide-react";

// ── Severity helpers ──────────────────────────────────────────────────

const SEVERITY_ORDER = { critical: 0, major: 1, moderate: 2, minor: 3 };
const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500/10 text-red-600 border-red-500/20",
  major:    "bg-orange-500/10 text-orange-600 border-orange-500/20",
  moderate: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  minor:    "bg-blue-500/10 text-blue-600 border-blue-500/20",
};
const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-red-500",
  major:    "bg-orange-500",
  moderate: "bg-amber-500",
  minor:    "bg-blue-500",
};
const LEVEL_ICON: Record<string, React.ReactNode> = {
  none:         <XCircle className="h-3.5 w-3.5 text-red-500" />,
  beginner:     <Minus className="h-3.5 w-3.5 text-amber-500" />,
  intermediate: <Minus className="h-3.5 w-3.5 text-amber-400" />,
  advanced:     <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />,
  expert:       <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />,
};

// ── Types for structured gap data ────────────────────────────────────

interface StructuredSkillGap {
  skill: string;
  required_level: string;
  current_level: string;
  gap_severity: string;
  importance_for_role: string;
  recommendation: string;
  estimated_time_to_close: string;
  learning_resources?: { platform: string; title: string; url: string; is_free: boolean; estimated_hours?: number }[];
}

interface AppWithGaps {
  id: string;
  jobTitle: string;
  company: string;
  compatibilityScore: number;
  skillGaps: StructuredSkillGap[];
  readinessLevel: string;
  updatedAt: number;
}

// ── Skill Gap Card ────────────────────────────────────────────────────

function GapCard({ gap, appCount }: { gap: StructuredSkillGap; appCount?: number }) {
  const [expanded, setExpanded] = useState(false);
  const sev = gap.gap_severity || "minor";

  return (
    <div className={cn("rounded-xl border p-4 transition-all", SEVERITY_COLOR[sev] ?? "bg-muted/30 border-border/30")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <span className={cn("mt-1.5 h-2 w-2 flex-shrink-0 rounded-full", SEVERITY_DOT[sev])} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-sm truncate">{gap.skill}</span>
              {appCount && appCount > 1 && (
                <Badge variant="outline" className="text-2xs px-1.5 py-0">
                  {appCount} apps
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 text-2xs text-muted-foreground">
              <span className="flex items-center gap-1">
                {LEVEL_ICON[gap.current_level] ?? LEVEL_ICON["none"]}
                Currently: {gap.current_level || "none"}
              </span>
              <span>→</span>
              <span className="flex items-center gap-1">
                {LEVEL_ICON[gap.required_level] ?? LEVEL_ICON["advanced"]}
                Need: {gap.required_level}
              </span>
              {gap.estimated_time_to_close && (
                <span className="ml-1 text-muted-foreground/70">~{gap.estimated_time_to_close}</span>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors mt-0.5"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 pt-3 border-t border-current/10 space-y-3"
        >
          {gap.recommendation && (
            <p className="text-xs text-muted-foreground">{gap.recommendation}</p>
          )}
          {gap.learning_resources && gap.learning_resources.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wide">Resources</p>
              {gap.learning_resources.slice(0, 3).map((r, i) => (
                <a
                  key={i}
                  href={r.url || "#"}
                  target={r.url && r.url !== "#" ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  className="flex items-center justify-between gap-2 rounded-lg bg-background/60 px-3 py-2 hover:bg-background transition-colors group"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate group-hover:text-primary transition-colors">{r.title}</p>
                    <p className="text-2xs text-muted-foreground flex items-center gap-1.5">
                      <span>{r.platform}</span>
                      {r.is_free && <Badge variant="outline" className="text-2xs px-1 py-0 border-emerald-500/30 text-emerald-600">Free</Badge>}
                      {r.estimated_hours && <span>~{r.estimated_hours}h</span>}
                    </p>
                  </div>
                  <ExternalLink className="h-3 w-3 text-muted-foreground/50 flex-shrink-0" />
                </a>
              ))}
            </div>
          )}
          <Link href="/learning" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <BookOpen className="h-3 w-3" /> Open in Learning Center
          </Link>
        </motion.div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────

export default function GapsPage() {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const { data: apps = [], loading } = useApplications(userId, 50);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  // Extract structured skill gaps from all applications
  const appsWithGaps = useMemo<AppWithGaps[]>(() => {
    return apps
      .filter(app => app.gaps)
      .map(app => {
        const gaps = app.gaps as any;
        const skillGaps: StructuredSkillGap[] = [];

        // Try structured skill_gaps first (new format with learning_resources)
        const structured = gaps?.skill_gaps ?? gaps?.skillGaps ?? [];
        if (Array.isArray(structured) && structured.length > 0) {
          structured.forEach((g: any) => {
            if (g?.skill) skillGaps.push(g);
          });
        } else {
          // Fall back to legacy missingKeywords
          const keywords: string[] = Array.isArray(gaps?.missingKeywords) ? gaps.missingKeywords : [];
          keywords.forEach(k => skillGaps.push({
            skill: k,
            required_level: "intermediate",
            current_level: "none",
            gap_severity: "moderate",
            importance_for_role: "important",
            recommendation: `Build skills in ${k} to improve your match for this role.`,
            estimated_time_to_close: "2-4 weeks",
          }));
        }

        return {
          id: app.id,
          jobTitle: app.confirmedFacts?.jobTitle || app.title || "Untitled Role",
          company: app.confirmedFacts?.company || "Unknown Company",
          compatibilityScore: gaps?.compatibility_score ?? gaps?.compatibility ?? 0,
          skillGaps: skillGaps.sort((a, b) =>
            (SEVERITY_ORDER[a.gap_severity as keyof typeof SEVERITY_ORDER] ?? 99)
            - (SEVERITY_ORDER[b.gap_severity as keyof typeof SEVERITY_ORDER] ?? 99)
          ),
          readinessLevel: gaps?.readiness_level ?? "competitive",
          updatedAt: app.updatedAt ?? 0,
        };
      })
      .filter(a => a.skillGaps.length > 0)
      .sort((a, b) => b.updatedAt - a.updatedAt);
  }, [apps]);

  // Cross-application skill frequency (how many apps share the same gap)
  const skillFrequency = useMemo(() => {
    const freq: Record<string, { count: number; maxSeverity: string; apps: string[] }> = {};
    appsWithGaps.forEach(app => {
      app.skillGaps.forEach(g => {
        const key = g.skill.toLowerCase();
        if (!freq[key]) freq[key] = { count: 0, maxSeverity: "minor", apps: [] };
        freq[key].count += 1;
        freq[key].apps.push(app.id);
        const cur = SEVERITY_ORDER[freq[key].maxSeverity as keyof typeof SEVERITY_ORDER] ?? 99;
        const next = SEVERITY_ORDER[g.gap_severity as keyof typeof SEVERITY_ORDER] ?? 99;
        if (next < cur) freq[key].maxSeverity = g.gap_severity;
      });
    });
    return Object.entries(freq)
      .filter(([, v]) => v.count > 1)
      .sort(([, a], [, b]) => b.count - a.count || (SEVERITY_ORDER[a.maxSeverity as keyof typeof SEVERITY_ORDER] ?? 99) - (SEVERITY_ORDER[b.maxSeverity as keyof typeof SEVERITY_ORDER] ?? 99))
      .slice(0, 10);
  }, [appsWithGaps]);

  const selectedApp = selectedAppId ? appsWithGaps.find(a => a.id === selectedAppId) : appsWithGaps[0] ?? null;
  const totalGaps = appsWithGaps.reduce((s, a) => s + a.skillGaps.length, 0);
  const criticalCount = appsWithGaps.reduce((s, a) => s + a.skillGaps.filter(g => g.gap_severity === "critical").length, 0);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl space-y-4">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-64 rounded-2xl" />)}
        </div>
      </div>
    );
  }

  if (appsWithGaps.length === 0) {
    return (
      <div className="container mx-auto px-4 py-16 max-w-3xl text-center space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto">
          <Target className="h-8 w-8 text-muted-foreground" />
        </div>
        <h1 className="text-2xl font-bold">Gaps Center</h1>
        <p className="text-muted-foreground">
          No gap analysis found yet. Generate a document pack for a job to see your skill gaps here.
        </p>
        <Button asChild>
          <Link href="/new">
            <Zap className="h-4 w-4 mr-2" /> Start a New Application
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Target className="h-6 w-6 text-primary" /> Gaps Center
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            {totalGaps} skill gap{totalGaps !== 1 ? "s" : ""} across {appsWithGaps.length} application{appsWithGaps.length !== 1 ? "s" : ""}
            {criticalCount > 0 && <span className="text-red-600 font-medium"> — {criticalCount} critical</span>}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/learning">
            <BookOpen className="h-4 w-4 mr-2" /> Learning Center
          </Link>
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Application list + cross-app frequency */}
        <div className="space-y-4">
          {/* Cross-app recurring gaps */}
          {skillFrequency.length > 0 && (
            <div className="rounded-2xl border bg-card p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" />
                <span className="font-semibold text-sm">Recurring Gaps</span>
                <Badge variant="secondary" className="text-2xs ml-auto">{skillFrequency.length}</Badge>
              </div>
              <p className="text-2xs text-muted-foreground">Skills missing in multiple applications</p>
              <div className="space-y-1.5">
                {skillFrequency.map(([skill, info]) => (
                  <div key={skill} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={cn("h-2 w-2 flex-shrink-0 rounded-full", SEVERITY_DOT[info.maxSeverity] ?? "bg-muted")} />
                      <span className="text-xs truncate capitalize">{skill}</span>
                    </div>
                    <Badge variant="outline" className="text-2xs flex-shrink-0">
                      {info.count} app{info.count !== 1 ? "s" : ""}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Application selector */}
          <div className="rounded-2xl border bg-card overflow-hidden">
            <div className="px-4 py-3 border-b bg-muted/30">
              <span className="text-sm font-medium">Applications</span>
            </div>
            <div className="divide-y">
              {appsWithGaps.map(app => (
                <button
                  key={app.id}
                  onClick={() => setSelectedAppId(app.id)}
                  className={cn(
                    "w-full text-left px-4 py-3 transition-colors hover:bg-muted/40",
                    (selectedApp?.id === app.id) && "bg-primary/5 border-l-2 border-l-primary"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{app.jobTitle}</p>
                      <p className="text-2xs text-muted-foreground truncate">{app.company}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className={cn(
                        "text-xs font-bold",
                        app.compatibilityScore >= 70 ? "text-emerald-600" :
                        app.compatibilityScore >= 50 ? "text-amber-600" : "text-red-600"
                      )}>
                        {app.compatibilityScore}%
                      </span>
                      <Badge variant="outline" className="text-2xs">
                        {app.skillGaps.length} gap{app.skillGaps.length !== 1 ? "s" : ""}
                      </Badge>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Gap details for selected app */}
        <div className="lg:col-span-2 space-y-4">
          {selectedApp ? (
            <>
              <div className="rounded-2xl border bg-card p-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <h2 className="font-bold text-lg">{selectedApp.jobTitle}</h2>
                    <p className="text-muted-foreground text-sm">{selectedApp.company}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-center">
                      <p className={cn(
                        "text-2xl font-black tabular-nums",
                        selectedApp.compatibilityScore >= 70 ? "text-emerald-600" :
                        selectedApp.compatibilityScore >= 50 ? "text-amber-600" : "text-red-600"
                      )}>
                        {selectedApp.compatibilityScore}%
                      </p>
                      <p className="text-2xs text-muted-foreground">Match</p>
                    </div>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/workspace/${selectedApp.id}`}>
                        Open Workspace <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                      </Link>
                    </Button>
                  </div>
                </div>

                {/* Severity breakdown */}
                <div className="grid grid-cols-4 gap-3 mt-4">
                  {(["critical", "major", "moderate", "minor"] as const).map(sev => {
                    const count = selectedApp.skillGaps.filter(g => g.gap_severity === sev).length;
                    return (
                      <div key={sev} className={cn("rounded-lg px-3 py-2 text-center border", SEVERITY_COLOR[sev])}>
                        <p className="text-lg font-bold">{count}</p>
                        <p className="text-2xs capitalize">{sev}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Skill gap cards */}
              <div className="space-y-2">
                {selectedApp.skillGaps.map((gap, i) => (
                  <motion.div
                    key={`${gap.skill}-${i}`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <GapCard
                      gap={gap}
                      appCount={skillFrequency.find(([s]) => s === gap.skill.toLowerCase())?.[1].count}
                    />
                  </motion.div>
                ))}
              </div>

              <div className="flex gap-3 pt-2">
                <Button asChild size="sm">
                  <Link href="/learning">
                    <TrendingUp className="h-4 w-4 mr-1.5" /> Go to Learning Center
                  </Link>
                </Button>
                <Button asChild size="sm" variant="outline">
                  <Link href={`/workspace/${selectedApp.id}`}>
                    <RefreshCw className="h-4 w-4 mr-1.5" /> Improve Documents
                  </Link>
                </Button>
              </div>
            </>
          ) : (
            <div className="rounded-2xl border bg-card flex items-center justify-center p-16 text-center text-muted-foreground">
              <div className="space-y-2">
                <AlertTriangle className="h-8 w-8 mx-auto text-muted-foreground/30" />
                <p>Select an application to see gap details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
