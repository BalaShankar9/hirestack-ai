"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight, Sparkles, Clock, Target, ShieldCheck, ScanEye, Award,
  Plus, Briefcase, TrendingUp, Trash2, Zap, FileSearch, FileText, MessageSquare,
  DollarSign, BookOpen, BarChart3, Brain, Flame,
  Bot, Activity, CheckCircle2, User, Bell, Gauge,
} from "lucide-react";
import { useAuth } from "@/components/providers";
import { computeEvidenceStrengthScore, useApplications, useEvidence, useTasks } from "@/lib/firestore";
import { deleteApplication, setTaskStatus, trackEvent } from "@/lib/firestore";
import { toast } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { TaskQueue } from "@/components/workspace/task-queue";
import { AITrace } from "@/components/ui/ai-trace";
import { cn } from "@/lib/utils";
import { useOnboarding } from "@/contexts/onboarding-context";
import { useAchievements, type Achievement } from "@/hooks/use-achievements";
import { AchievementToast } from "@/components/ui/achievement-toast";
import api from "@/lib/api";
import type { Profile } from "@/types";

/* ── Helpers ──────────────────────────────────────────────────────── */

function formatRelativeTime(ts: number | string): string {
  try {
    const d = typeof ts === "string" ? new Date(ts) : new Date(ts);
    const diff = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diff < 1) return "Just now";
    if (diff < 60) return `${diff}m ago`;
    if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
    if (diff < 10080) return `${Math.floor(diff / 1440)}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch { return "Recently"; }
}

function scoreColor(v: number) {
  if (v >= 80) return "text-emerald-500";
  if (v >= 60) return "text-blue-500";
  if (v >= 40) return "text-amber-500";
  return "text-rose-500";
}

function scoreBg(v: number) {
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-blue-500";
  if (v >= 40) return "bg-amber-500";
  return "bg-rose-500";
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/* ── Career Pulse Ring ────────────────────────────────────────────── */

function CareerPulse({ value }: { value: number }) {
  const r = 52, circ = 2 * Math.PI * r, offset = circ - (value / 100) * circ;
  const color = value >= 75 ? "stroke-emerald-500" : value >= 50 ? "stroke-teal-500" : value >= 25 ? "stroke-amber-500" : "stroke-rose-500";
  return (
    <div className="relative h-[120px] w-[120px]">
      <svg width={120} height={120} className="-rotate-90">
        <circle cx={60} cy={60} r={r} strokeWidth={8} fill="none" className="stroke-white/10" />
        <circle cx={60} cy={60} r={r} strokeWidth={8} fill="none" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          className={cn("transition-all duration-1000 ease-out", color)} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold tabular-nums text-white">{value}</span>
        <span className="text-[9px] text-white/50 uppercase tracking-widest shimmer-text">Career Pulse</span>
      </div>
    </div>
  );
}

/* ── Quick Actions ────────────────────────────────────────────────── */

const QUICK_ACTIONS = [
  { href: "/new", label: "New Application", icon: Plus, color: "bg-primary/10 text-primary" },
  { href: "/ats-scanner", label: "ATS Check", icon: FileSearch, color: "bg-cyan-500/10 text-cyan-500" },
  { href: "/interview", label: "Interview Prep", icon: MessageSquare, color: "bg-blue-500/10 text-blue-500" },
  { href: "/salary", label: "Salary Coach", icon: DollarSign, color: "bg-amber-500/10 text-amber-500" },
  { href: "/evidence", label: "Evidence", icon: ShieldCheck, color: "bg-violet-500/10 text-violet-500" },
  { href: "/nexus", label: "Profile", icon: User, color: "bg-teal-500/10 text-teal-500" },
  { href: "/job-board", label: "Job Board", icon: Briefcase, color: "bg-emerald-500/10 text-emerald-500" },
  { href: "/career-analytics", label: "Analytics", icon: BarChart3, color: "bg-rose-500/10 text-rose-500" },
  { href: "/learning", label: "Daily Learn", icon: BookOpen, color: "bg-orange-500/10 text-orange-500" },
  { href: "/gaps", label: "Gap Report", icon: Brain, color: "bg-indigo-500/10 text-indigo-500" },
] as const;

/* ── Page ─────────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const router = useRouter();
  const { user, session: authSession } = useAuth();
  const userId = user?.uid || user?.id || null;
  const userRole = user?.user_metadata?.role as string | undefined;

  const { data: apps = [], loading: appsLoading, removeItem: removeApp } = useApplications(userId, 50);
  const { data: tasks = [], loading: tasksLoading } = useTasks(userId, null, 200);
  const { data: evidence = [], loading: evidenceLoading } = useEvidence(userId, 200);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [briefing, setBriefing] = useState<any>(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [streak, setStreak] = useState<{ current_streak: number; longest_streak: number; total_points: number; level: number } | null>(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [funnel, setFunnel] = useState<{ funnel: Record<string, number>; conversion_rates: Record<string, number>; total_signals: number } | null>(null);
  const [telemetry, setTelemetry] = useState<{ total_runs: number; total_cost_usd_cents: number; total_tokens: number; by_pipeline: Record<string, any> } | null>(null);
  const [pipelineHealth, setPipelineHealth] = useState<{ health_score: number; status: string; alerts: Array<{ type: string; severity: string; message: string }> } | null>(null);
  const [tuning, setTuning] = useState<{ recommendation: string; confidence: string; reason: string; config: Record<string, any>; stats?: Record<string, any> } | null>(null);
  const [predictions, setPredictions] = useState<Record<string, { prediction: number; confidence: string }>>({});
  const [alertSummary, setAlertSummary] = useState<{ total: number; unread: number; by_severity: Record<string, number>; by_type: Record<string, number> } | null>(null);
  const [momentum, setMomentum] = useState<{ score: number; trend: string; components: Record<string, number> } | null>(null);

  // Achievement system state
  const [pendingAchievement, setPendingAchievement] = useState<Achievement | null>(null);
  const handleAchievementUnlock = useCallback((a: Achievement) => {
    setPendingAchievement(a);
  }, []);

  // Fetch profile to check onboarding step 2
  useEffect(() => {
    if (!userId) return;
    api.profile.get()
      .then((p: Profile) => { if (p?.raw_resume_text) setHasProfile(true); })
      .catch(() => {});
  }, [userId]);

  const [showAllApps, setShowAllApps] = useState(false);
  const openTasks = useMemo(() => tasks.filter((t) => t.status === "todo"), [tasks]);
  const topApps = useMemo(() => showAllApps ? apps : apps.slice(0, 8), [apps, showAllApps]);

  const stats = useMemo(() => {
    try {
      const active = apps.filter((a) => a.status !== "archived").length;
      const avgMatch = apps.length === 0 ? 0 : Math.round(apps.reduce((s, a) => s + (a.scores?.match ?? 0), 0) / apps.length);
      // Career Pulse: weighted health score
      const completeness = Math.min(100, active * 15);
      const matchHealth = avgMatch;
      const evidenceHealth = Math.min(100, evidence.length * 12);
      const taskHealth = openTasks.length > 0 ? Math.max(0, 100 - openTasks.length * 8) : 100;
      const pulse = Math.round(completeness * 0.2 + matchHealth * 0.4 + evidenceHealth * 0.2 + taskHealth * 0.2);
      return { apps: active, openTasks: openTasks.length, evidence: evidence.length, avgMatch, pulse };
    } catch (e) {
      console.error("[DashboardPage] Failed to compute stats:", e);
      return { apps: 0, openTasks: 0, evidence: 0, avgMatch: 0, pulse: 0 };
    }
  }, [apps, evidence.length, openTasks.length]);

  // Best scores for achievement checks
  const bestAtsScore = useMemo(() => Math.max(0, ...apps.map((a) => a.scores?.atsReadiness ?? 0)), [apps]);
  const bestMatchScore = useMemo(() => Math.max(0, ...apps.map((a) => a.scores?.match ?? 0)), [apps]);

  // Achievement system
  useAchievements({
    userId: userId ?? "",
    appCount: stats.apps,
    evidenceCount: stats.evidence,
    streak: streak?.current_streak ?? 0,
    profilePct: 0, // profile completeness checked when profile loads
    bestAtsScore,
    bestMatchScore,
    onUnlock: handleAchievementUnlock,
  });

  // Load AI briefing
  useEffect(() => {
    if (!userId || briefing) return;
    const token = authSession?.access_token;
    if (!token) return;
    setBriefingLoading(true);
    const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
    fetch(`${API_URL}/api/analytics/daily-briefing`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => setBriefing(d))
      .catch(() => { setBriefing(null); })
      .finally(() => setBriefingLoading(false));
  }, [userId, briefing, authSession?.access_token]);

  // Load learning streak
  useEffect(() => {
    if (!userId) return;
    const token = authSession?.access_token;
    if (!token) return;
    const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
    fetch(`${API_URL}/api/learning/streak`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setStreak(d))
      .catch((e) => console.error("Failed to load learning streak", e));
  }, [userId, authSession?.access_token]);

  // Load conversion funnel + pipeline telemetry + health + tuning
  useEffect(() => {
    if (!userId) return;
    api.career.conversionFunnel()
      .then((d: any) => d && setFunnel(d))
      .catch(() => {});
    api.career.telemetrySummary(30)
      .then((d: any) => d && setTelemetry(d))
      .catch(() => {});
    api.career.pipelineHealth()
      .then((d: any) => d && setPipelineHealth(d))
      .catch(() => {});
    api.career.tuningRecommendation()
      .then((d: any) => d && setTuning(d))
      .catch(() => {});
    api.career.alertSummary()
      .then((d: any) => d && setAlertSummary(d))
      .catch(() => {});
    api.career.careerMomentum()
      .then((d: any) => d && setMomentum(d))
      .catch(() => {});
  }, [userId]);

  // Load interview predictions for visible apps (max 8 to avoid request storms)
  useEffect(() => {
    if (!userId || apps.length === 0) return;
    const toPredict = apps.slice(0, 8);
    toPredict.forEach((a) => {
      if (predictions[a.id]) return; // already fetched
      api.career.predictInterview(a.id)
        .then((d: any) => {
          if (d && typeof d.prediction === "number") {
            setPredictions((prev) => ({ ...prev, [a.id]: { prediction: d.prediction, confidence: d.confidence } }));
          }
        })
        .catch(() => {});
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, apps.length]);

  const handleDelete = async () => {
    if (!deleteTarget || !userId) return;
    setDeleting(true);
    try {
      await deleteApplication(deleteTarget.id);
      removeApp(deleteTarget.id);
      toast.success("Workspace deleted");
    } catch (err: any) { toast.error("Delete failed", err?.message); }
    finally { setDeleting(false); setDeleteTarget(null); }
  };

  const userName = user?.user_metadata?.full_name || user?.full_name || user?.email?.split("@")[0] || "";

  // Update onboarding context with real data
  const { stage: onboardingStage, updateCounts } = useOnboarding();
  useEffect(() => {
    if (!appsLoading && !evidenceLoading) {
      updateCounts({
        applications: apps.length,
        hasProfile,
        hasEvidence: evidence.length > 0,
      });
    }
  }, [apps.length, evidence.length, appsLoading, evidenceLoading, hasProfile, updateCounts]);

  const isNewUser = !appsLoading && apps.length === 0;

  // Show loading skeleton while initial data loads to prevent flicker between new/existing user views
  if (appsLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 rounded-3xl" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
        </div>
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    );
  }

  // ── New User: Onboarding-first experience ──
  if (isNewUser) {
    return (
      <div className="space-y-6">
        {/* Welcome + primary CTA */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="rounded-3xl border bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-5 sm:p-6 text-white shadow-glow-md overflow-hidden relative"
        >
          <div className="absolute inset-0 opacity-[0.03] bg-dot-grid" />
          <div className="relative max-w-2xl">
            <h1 className="text-2xl font-bold sm:text-3xl">
              Welcome{userName ? `, ${userName}` : ""}
            </h1>
            <p className="mt-3 text-base text-white/80 leading-relaxed">
              Build your first proof-backed application in minutes.
              Paste a job description, add your resume, and get tailored documents
              with gap analysis, evidence mapping, and ATS optimization.
            </p>
            <Button
              className="mt-6 bg-white text-primary hover:bg-white/90 shadow-sm gap-2"
              onClick={() => router.push("/new")}
            >
              Start your first application
              <ArrowRight className="h-4 w-4" />
            </Button>
            <a
              href="https://www.youtube.com/@HireStackAI"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-white transition-colors"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
              Watch a 60-second demo →
            </a>
          </div>
        </motion.div>

        {/* Setup progress steps */}
        <div className="rounded-2xl border bg-card p-6">
          <h2 className="text-sm font-semibold mb-4">Get started in 3 steps</h2>
          <div className="space-y-3">
            {[
              {
                step: 1,
                title: "Paste a job description",
                desc: "Drop in any JD — AI extracts every requirement, keyword, and expectation.",
                done: apps.length > 0,
                href: "/new",
              },
              {
                step: 2,
                title: "Add your resume or profile",
                desc: "Upload a resume or set up your profile so documents are tailored to your experience.",
                done: hasProfile,
                href: "/nexus",
              },
              {
                step: 3,
                title: "Review your application workspace",
                desc: "Get fit analysis, tailored documents, gap report, and evidence suggestions.",
                done: apps.some((a: any) => a.modules?.cv?.state === "ready"),
                href: apps.length > 0 ? `/applications/${apps[0].id}` : null,
              },
            ].map((item) => (
              <div
                key={item.step}
                className={cn(
                  "flex items-start gap-4 rounded-xl border p-4 transition-colors",
                  item.done ? "bg-emerald-500/5 border-emerald-500/20" : "hover:bg-muted/30"
                )}
              >
                <div className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                  item.done
                    ? "bg-emerald-500 text-white"
                    : "bg-primary/10 text-primary"
                )}>
                  {item.done ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    item.step
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
                </div>
                {item.href && !item.done && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 rounded-xl text-xs"
                    onClick={() => router.push(item.href!)}
                  >
                    {item.step === 1 ? "Start" : "Set up"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Sample preview: what you'll get */}
        <div className="rounded-2xl border bg-card p-6">
          <h2 className="text-sm font-semibold mb-1">What you&apos;ll get</h2>
          <p className="text-xs text-muted-foreground mb-4">
            Each application generates a complete workspace with these outputs:
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 animate-stagger">
            {[
              { icon: Target, label: "Fit Analysis", desc: "Match score vs job requirements", color: "text-emerald-500 bg-emerald-500/10" },
              { icon: FileSearch, label: "ATS Optimization", desc: "Keyword coverage & format fixes", color: "text-blue-500 bg-blue-500/10" },
              { icon: ShieldCheck, label: "Evidence Mapping", desc: "Proof attached to every claim", color: "text-violet-500 bg-violet-500/10" },
              { icon: Briefcase, label: "Tailored Documents", desc: "CV, cover letter & more", color: "text-primary bg-primary/10" },
              { icon: TrendingUp, label: "Gap Report", desc: "What to improve before applying", color: "text-amber-500 bg-amber-500/10" },
              { icon: MessageSquare, label: "Interview Prep", desc: "Predicted questions & answers", color: "text-rose-500 bg-rose-500/10" },
            ].map((item) => (
              <div key={item.label} className="flex items-start gap-3 rounded-xl bg-muted/20 p-3 card-spotlight scroll-reveal">
                <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", item.color)}>
                  <item.icon className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold">{item.label}</p>
                  <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Hero Command Center ──────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
          className="rounded-3xl border bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-5 sm:p-8 text-white shadow-glow-md overflow-hidden relative"
      >
        {/* Decorative grid */}
        <div className="absolute inset-0 opacity-[0.03] bg-dot-grid" />

        <div className="relative flex flex-col lg:flex-row lg:items-center gap-6">
          {/* Career Pulse */}
          <CareerPulse value={stats.pulse} />

          {/* Greeting + Briefing */}
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-semibold">
              {greeting()}{userName ? `, ${userName}` : ""}
            </h1>
            {/* AI Briefing */}
            {briefing?.insight ? (
              <div className="mt-2 flex items-start gap-2 rounded-xl bg-white/10 backdrop-blur-sm px-3.5 py-2.5 border border-white/10">
                <Brain className="h-4 w-4 text-white/70 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/90 leading-relaxed">{briefing.insight}</p>
                  {briefing.action_href && (
                    <Link href={briefing.action_href} className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white mt-1 transition-colors">
                      {briefing.action_label || "Learn more"} <ArrowRight className="h-3 w-3" />
                    </Link>
                  )}
                </div>
              </div>
            ) : briefingLoading ? (
              <div className="mt-2 flex items-center gap-2 text-sm text-white/50">
                <Bot className="h-4 w-4 animate-pulse" /> Generating your daily insight...
              </div>
            ) : (
              <p className="mt-2 text-sm text-white/60">
                {stats.apps === 0 ? "Start your first application to unlock AI-powered career intelligence." : `${stats.apps} active workspaces with ${stats.avgMatch}% average match.`}
              </p>
            )}
          </div>

          <Button className="bg-white text-primary hover:bg-white/90 shadow-sm shrink-0" onClick={() => router.push("/new")}>
            New application <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>

        {/* Stats row */}
        <div className="relative mt-5 grid gap-2 grid-cols-3 md:grid-cols-6">
          {[
            { icon: Briefcase, label: "Applications", value: stats.apps },
            { icon: Target, label: "Avg Match", value: `${stats.avgMatch}%` },
            { icon: Zap, label: "Open Tasks", value: stats.openTasks, accent: stats.openTasks > 0 },
            { icon: ShieldCheck, label: "Evidence", value: stats.evidence },
            { icon: ScanEye, label: "Completed", value: tasks.filter(t => t.status === "done").length },
            { icon: Activity, label: "Career Pulse", value: `${stats.pulse}%` },
          ].map((s) => (
            <div key={s.label} className={cn("rounded-xl border border-white/10 bg-white/10 p-3 backdrop-blur-sm glass-depth", s.accent && "border-white/20 bg-white/15")}>
              <div className="flex items-center gap-1.5 text-[10px] text-white/50">
                <s.icon className="h-3 w-3" /> {s.label}
              </div>
              <div className="mt-0.5 text-xl font-bold tabular-nums">{s.value}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ── Quick Actions ─────────────────────────────────────── */}
      <div className="grid grid-cols-4 xs:grid-cols-5 md:grid-cols-10 gap-2">
        {QUICK_ACTIONS.map((a, i) => (
          <motion.div
            key={a.href}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.05 }}
          >
            <Link href={a.href} className="group flex flex-col items-center gap-2 rounded-xl border bg-card p-3 hover:border-primary/20 hover:shadow-soft-sm hover:-translate-y-0.5 transition-all duration-300 card-spotlight glow-border-hover">
              <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg transition-transform group-hover:scale-110", a.color)}>
                <a.icon className="h-4 w-4" />
              </div>
              <span className="text-[11px] font-medium text-muted-foreground group-hover:text-foreground transition-colors text-center leading-tight">{a.label}</span>
            </Link>
          </motion.div>
        ))}
      </div>

      {/* ── Main Grid ─────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        {/* Left: Workspaces */}
        <div className="space-y-4 min-w-0">
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold truncate">Applications</h2>
              <p className="text-xs text-muted-foreground">Your active application workspaces</p>
            </div>
            {topApps.length > 0 && (
              <Button variant="outline" size="sm" className="gap-1.5 rounded-xl text-xs shrink-0" onClick={() => router.push("/new")}>
                <Plus className="h-3 w-3" /> New
              </Button>
            )}
          </div>

          {appsLoading ? (
            <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
          ) : topApps.length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-card/50 p-6 sm:p-10 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                <Briefcase className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mt-4 text-sm font-semibold">No applications yet</h3>
              <p className="mt-1 text-xs text-muted-foreground max-w-sm mx-auto">Paste a job description and let AI build your complete application.</p>
              <Button className="mt-4 gap-2 rounded-xl" onClick={() => router.push("/new")}>Start <ArrowRight className="h-4 w-4" /></Button>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {topApps.map((a) => {
                const title = a.title || a.confirmedFacts?.jobTitle || "Untitled";
                const company = a.confirmedFacts?.company;
                const match = a.scores?.match ?? 0;
                const proof = Array.isArray(a.benchmark?.keywords) && a.benchmark!.keywords.length > 0
                  ? computeEvidenceStrengthScore({ evidence, keywords: a.benchmark!.keywords })
                  : (a.scores?.evidenceStrength ?? 0);

                return (
                  <div key={a.id} className="group relative rounded-2xl border bg-card p-4 shadow-soft-sm hover:shadow-soft-md hover:border-primary/20 hover:-translate-y-0.5 transition-all duration-300 card-spotlight">
                    <button type="button" onClick={(e) => { e.preventDefault(); setDeleteTarget({ id: a.id, title }); }}
                      aria-label={`Delete ${title}`}
                      className="absolute right-3 top-3 z-10 h-6 w-6 flex items-center justify-center rounded-lg opacity-0 group-hover:opacity-100 sm:opacity-0 [@media(pointer:coarse)]:opacity-100 hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      <Trash2 className="h-3 w-3" />
                    </button>
                    <Link href={`/applications/${a.id}`} className="block">
                      <div className="flex items-start justify-between gap-2 pr-6">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <p className="text-sm font-semibold truncate group-hover:text-primary transition-colors">{title}</p>
                            {a.status === "draft" && (
                              <Badge variant="secondary" className="text-[9px] px-1.5 py-0 bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20">Draft</Badge>
                            )}
                            {a.status === "archived" && (
                              <Badge variant="secondary" className="text-[9px] px-1.5 py-0 bg-muted text-muted-foreground border-border">Archived</Badge>
                            )}
                          </div>
                          {company && <p className="text-xs text-muted-foreground truncate mt-0.5">{company}</p>}
                        </div>
                        <Badge className={cn("border text-[11px] shrink-0 tabular-nums",
                          match >= 80 ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                          match >= 60 ? "bg-blue-500/10 text-blue-500 border-blue-500/20" :
                          match >= 40 ? "bg-amber-500/10 text-amber-500 border-amber-500/20" :
                          "bg-rose-500/10 text-rose-500 border-rose-500/20"
                        )} variant="secondary">{match}%</Badge>
                      </div>
                      {/* Interview Prediction Badge */}
                      {predictions[a.id] && (
                        <div className="flex items-center gap-1 mt-1">
                          <Sparkles className="h-2.5 w-2.5 text-violet-400" />
                          <span className={cn("text-[10px] font-medium tabular-nums",
                            predictions[a.id].prediction >= 60 ? "text-emerald-500" :
                            predictions[a.id].prediction >= 30 ? "text-amber-500" : "text-rose-400"
                          )}>
                            {predictions[a.id].prediction}% interview likelihood
                          </span>
                        </div>
                      )}
                      <div className="mt-2.5 h-1 rounded-full bg-muted overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all", scoreBg(match))} style={{ width: `${match}%` }} />
                      </div>
                      <div className="mt-2 grid grid-cols-2 xs:grid-cols-4 gap-1.5">
                        {[
                          { icon: Target, label: "Match", val: match },
                          { icon: ShieldCheck, label: "ATS", val: a.scores?.atsReadiness ?? 0 },
                          { icon: ScanEye, label: "Scan", val: a.scores?.recruiterScan ?? 0 },
                          { icon: Award, label: "Proof", val: proof },
                        ].map((m) => (
                          <div key={m.label} className="rounded-lg bg-muted/30 p-1.5 text-center min-w-0">
                            <div className="flex items-center justify-center gap-0.5 text-muted-foreground"><m.icon className="h-2.5 w-2.5 shrink-0" /><span className="text-[9px] truncate">{m.label}</span></div>
                            <div className={cn("text-[11px] font-semibold tabular-nums", scoreColor(m.val))}>{m.val}%</div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
                        <span className="flex items-center gap-1"><Clock className="h-2.5 w-2.5" /> {formatRelativeTime(a.updatedAt)}</span>
                        {(() => {
                          const coreCount = [a.cvHtml, a.coverLetterHtml, a.personalStatementHtml, a.portfolioHtml].filter(Boolean).length;
                          const extraCount = Object.keys(a.generatedDocuments || {}).length;
                          const total = coreCount + extraCount;
                          if (total === 0) return null;
                          return (
                            <span className="flex items-center gap-1">
                              <FileText className="h-2.5 w-2.5" />
                              {total} doc{total !== 1 ? "s" : ""}
                            </span>
                          );
                        })()}
                      </div>
                    </Link>
                  </div>
                );
              })}
            </div>
          )}
          {apps.length > 8 && (
            <div className="text-center">
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => setShowAllApps(!showAllApps)}
              >
                {showAllApps ? "Show less" : `View all ${apps.length} applications`}
              </Button>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="space-y-4 min-w-0">
          <TaskQueue tasks={openTasks.slice(0, 12)} onOpenWorkspace={(id) => router.push(`/applications/${id}`)}
            onToggle={async (t) => { try { await setTaskStatus(userId!, t.id, t.status === "done" ? "todo" : "done"); } catch {} }} compact />

          <Link href="/evidence" className="block rounded-2xl border bg-card p-4 hover:border-violet-500/20 hover:shadow-soft-sm hover:-translate-y-0.5 transition-all duration-300 glow-border-hover">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10"><ShieldCheck className="h-4 w-4 text-violet-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Evidence</p><p className="text-[11px] text-muted-foreground">{evidence.length} proof items collected</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          <Link href="/nexus" className="block rounded-2xl border bg-card p-4 hover:border-teal-500/20 hover:shadow-soft-sm hover:-translate-y-0.5 transition-all duration-300 glow-border-hover">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500/10"><User className="h-4 w-4 text-teal-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Profile</p><p className="text-[11px] text-muted-foreground">Your career identity & resume</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          <Link href="/career-analytics" className="block rounded-2xl border bg-card p-4 hover:border-blue-500/20 hover:shadow-soft-sm hover:-translate-y-0.5 transition-all duration-300 glow-border-hover">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10"><BarChart3 className="h-4 w-4 text-blue-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Progress</p><p className="text-[11px] text-muted-foreground">Track readiness over time</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          {/* Conversion Funnel — closed-loop tracking */}
          {funnel && funnel.total_signals > 0 && (
            <div className="rounded-2xl border bg-card p-4 space-y-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10"><TrendingUp className="h-3.5 w-3.5 text-emerald-500" /></div>
                <p className="text-sm font-semibold">Outcome Funnel</p>
              </div>
              <div className="space-y-1.5">
                {(["exported", "applied", "screened", "interview", "offer", "accepted"] as const).map((stage) => {
                  const count = funnel.funnel[stage] || 0;
                  const maxCount = Math.max(1, funnel.funnel["exported"] || 1);
                  const pct = Math.round((count / maxCount) * 100);
                  return (
                    <div key={stage} className="flex items-center gap-2 text-[11px]">
                      <span className="w-16 text-muted-foreground capitalize">{stage}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-500/70 transition-all duration-700" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-6 text-right tabular-nums font-medium">{count}</span>
                    </div>
                  );
                })}
              </div>
              {funnel.conversion_rates.exported_to_applied > 0 && (
                <p className="text-[10px] text-muted-foreground">
                  Apply rate: <span className="font-semibold text-emerald-500">{funnel.conversion_rates.exported_to_applied}%</span>
                  {funnel.conversion_rates.interview_to_offer > 0 && (
                    <> · Offer rate: <span className="font-semibold text-emerald-500">{funnel.conversion_rates.interview_to_offer}%</span></>
                  )}
                </p>
              )}
            </div>
          )}

          {/* Pipeline Telemetry Summary — admin/enterprise only (internal cost data) */}
          {(userRole === "admin" || userRole === "enterprise") && telemetry && telemetry.total_runs > 0 && (
            <div className="rounded-2xl border bg-card p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500/10"><Activity className="h-3.5 w-3.5 text-cyan-500" /></div>
                <p className="text-sm font-semibold">AI Usage (30d)</p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-lg font-bold tabular-nums">{telemetry.total_runs}</p>
                  <p className="text-[10px] text-muted-foreground">Runs</p>
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">{(telemetry.total_tokens / 1000).toFixed(0)}k</p>
                  <p className="text-[10px] text-muted-foreground">Tokens</p>
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">${(telemetry.total_cost_usd_cents / 100).toFixed(2)}</p>
                  <p className="text-[10px] text-muted-foreground">Cost</p>
                </div>
              </div>
            </div>
          )}

          {/* Pipeline Health Monitor — admin/enterprise only */}
          {(userRole === "admin" || userRole === "enterprise") && pipelineHealth && (
            <div className={cn(
              "rounded-2xl border bg-card p-4 space-y-2",
              pipelineHealth.status === "unhealthy" && "border-rose-500/30",
              pipelineHealth.status === "degraded" && "border-amber-500/30",
            )}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-lg",
                    pipelineHealth.status === "healthy" ? "bg-emerald-500/10" :
                    pipelineHealth.status === "degraded" ? "bg-amber-500/10" : "bg-rose-500/10",
                  )}>
                    <Activity className={cn(
                      "h-3.5 w-3.5",
                      pipelineHealth.status === "healthy" ? "text-emerald-500" :
                      pipelineHealth.status === "degraded" ? "text-amber-500" : "text-rose-500",
                    )} />
                  </div>
                  <p className="text-sm font-semibold">Pipeline Health</p>
                </div>
                <Badge variant="secondary" className={cn(
                  "text-[10px] px-1.5 py-0",
                  pipelineHealth.status === "healthy" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                  pipelineHealth.status === "degraded" ? "bg-amber-500/10 text-amber-500 border-amber-500/20" :
                  "bg-rose-500/10 text-rose-500 border-rose-500/20",
                )}>
                  {pipelineHealth.health_score}%
                </Badge>
              </div>
              {pipelineHealth.alerts.length > 0 ? (
                <div className="space-y-1">
                  {pipelineHealth.alerts.slice(0, 3).map((alert, i) => (
                    <div key={i} className={cn(
                      "text-[11px] rounded-lg px-2 py-1",
                      alert.severity === "high" ? "bg-rose-500/10 text-rose-400" : "bg-amber-500/10 text-amber-400",
                    )}>
                      {alert.message}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-muted-foreground">All systems nominal — no regressions detected.</p>
              )}
            </div>
          )}

          {/* Self-Tuning Recommendation — admin/enterprise only */}
          {(userRole === "admin" || userRole === "enterprise") && tuning && tuning.recommendation === "tuned" && (
            <div className="rounded-2xl border bg-gradient-to-br from-violet-500/5 to-indigo-500/5 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/10"><Brain className="h-3.5 w-3.5 text-violet-500" /></div>
                <p className="text-sm font-semibold">AI Self-Tuning</p>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-violet-500/10 text-violet-500 border-violet-500/20 ml-auto">
                  {tuning.confidence}
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">{tuning.reason}</p>
              {tuning.config && Object.keys(tuning.config).length > 0 && (
                <div className="grid grid-cols-3 gap-1 text-center">
                  {tuning.config.model && (
                    <div className="rounded-lg bg-muted/30 p-1.5">
                      <p className="text-[9px] text-muted-foreground">Model</p>
                      <p className="text-[11px] font-medium truncate">{tuning.config.model.replace("gemini-2.5-", "")}</p>
                    </div>
                  )}
                  {tuning.config.research_depth && (
                    <div className="rounded-lg bg-muted/30 p-1.5">
                      <p className="text-[9px] text-muted-foreground">Depth</p>
                      <p className="text-[11px] font-medium capitalize">{tuning.config.research_depth}</p>
                    </div>
                  )}
                  {tuning.config.max_iterations && (
                    <div className="rounded-lg bg-muted/30 p-1.5">
                      <p className="text-[9px] text-muted-foreground">Iterations</p>
                      <p className="text-[11px] font-medium">{tuning.config.max_iterations}</p>
                    </div>
                  )}
                </div>
              )}
              {tuning.stats && (
                <p className="text-[10px] text-muted-foreground">
                  Avg outcome: <span className="font-semibold text-violet-500">{tuning.stats.avg_outcome_score}</span>
                  {" · "}Configs tested: <span className="font-semibold">{tuning.stats.configs_evaluated}</span>
                </p>
              )}
            </div>
          )}

          {/* Career Alerts */}
          {alertSummary && alertSummary.total > 0 && (
            <div className={cn(
              "rounded-2xl border bg-card p-4 space-y-2",
              (alertSummary.by_severity?.critical ?? 0) > 0 && "border-rose-500/30",
              (alertSummary.by_severity?.warning ?? 0) > 0 && !(alertSummary.by_severity?.critical) && "border-amber-500/30",
            )}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-lg",
                    (alertSummary.by_severity?.critical ?? 0) > 0 ? "bg-rose-500/10" : "bg-amber-500/10",
                  )}>
                    <Bell className={cn(
                      "h-3.5 w-3.5",
                      (alertSummary.by_severity?.critical ?? 0) > 0 ? "text-rose-500" : "text-amber-500",
                    )} />
                  </div>
                  <p className="text-sm font-semibold">Career Alerts</p>
                </div>
                <div className="flex items-center gap-1">
                  {alertSummary.unread > 0 && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-primary/10 text-primary border-primary/20">
                      {alertSummary.unread} new
                    </Badge>
                  )}
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {alertSummary.total} total
                  </Badge>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-1 text-center">
                {(alertSummary.by_severity?.critical ?? 0) > 0 && (
                  <div className="rounded-lg bg-rose-500/10 p-1.5">
                    <p className="text-[9px] text-rose-400">Critical</p>
                    <p className="text-sm font-bold text-rose-500">{alertSummary.by_severity.critical}</p>
                  </div>
                )}
                {(alertSummary.by_severity?.warning ?? 0) > 0 && (
                  <div className="rounded-lg bg-amber-500/10 p-1.5">
                    <p className="text-[9px] text-amber-400">Warning</p>
                    <p className="text-sm font-bold text-amber-500">{alertSummary.by_severity.warning}</p>
                  </div>
                )}
                {(alertSummary.by_severity?.info ?? 0) > 0 && (
                  <div className="rounded-lg bg-blue-500/10 p-1.5">
                    <p className="text-[9px] text-blue-400">Info</p>
                    <p className="text-sm font-bold text-blue-500">{alertSummary.by_severity.info}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Career Momentum */}
          {momentum && (
            <div className="rounded-2xl border bg-gradient-to-br from-teal-500/5 to-emerald-500/5 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10">
                    <Gauge className="h-3.5 w-3.5 text-teal-500" />
                  </div>
                  <p className="text-sm font-semibold">Career Momentum</p>
                </div>
                <Badge variant="secondary" className={cn(
                  "text-[10px] px-1.5 py-0",
                  momentum.trend === "accelerating" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                  momentum.trend === "steady" ? "bg-teal-500/10 text-teal-500 border-teal-500/20" :
                  momentum.trend === "decelerating" ? "bg-amber-500/10 text-amber-500 border-amber-500/20" :
                  "bg-rose-500/10 text-rose-500 border-rose-500/20"
                )}>
                  {momentum.trend}
                </Badge>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative h-12 w-12">
                  <svg width={48} height={48} className="-rotate-90">
                    <circle cx={24} cy={24} r={18} strokeWidth={4} fill="none" className="stroke-white/10" />
                    <circle cx={24} cy={24} r={18} strokeWidth={4} fill="none" strokeLinecap="round"
                      strokeDasharray={2 * Math.PI * 18}
                      strokeDashoffset={2 * Math.PI * 18 - (momentum.score / 100) * 2 * Math.PI * 18}
                      className={cn("transition-all duration-700",
                        momentum.score >= 70 ? "stroke-emerald-500" : momentum.score >= 40 ? "stroke-teal-500" : "stroke-amber-500"
                      )} />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-sm font-bold tabular-nums">{momentum.score}</span>
                  </div>
                </div>
                {momentum.components && (
                  <div className="flex-1 space-y-1">
                    {Object.entries(momentum.components).slice(0, 4).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-2">
                        <p className="text-[9px] text-muted-foreground w-20 truncate capitalize">{key.replace(/_/g, " ")}</p>
                        <div className="flex-1 h-1 rounded-full bg-muted/30">
                          <div className="h-full rounded-full bg-teal-500/60 transition-all" style={{ width: `${Math.min(100, ((val as number) / 20) * 100)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Learning Streak / Daily Challenge */}
          {streak ? (
            streak.current_streak > 0 || streak.total_points > 0 ? (
              <Link href="/learning" className="block rounded-2xl border bg-gradient-to-br from-amber-500/5 to-orange-500/5 p-4 hover:border-amber-500/20 hover:shadow-soft-sm hover:-translate-y-0.5 transition-all duration-300 glow-border-hover">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10"><Flame className="h-4 w-4 text-amber-500" /></div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">Learning Streak</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[11px] text-muted-foreground"><span className="font-bold text-amber-500">{streak.current_streak}</span> day streak</span>
                      <span className="text-[11px] text-muted-foreground">Lv.{streak.level}</span>
                      <span className="text-[11px] text-muted-foreground">{streak.total_points} pts</span>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </Link>
            ) : (
              <Link href="/learning" className="block rounded-2xl border border-dashed border-amber-500/20 bg-gradient-to-br from-amber-500/5 to-orange-500/5 p-4 hover:border-amber-500/40 hover:-translate-y-0.5 transition-all duration-300">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10"><Flame className="h-4 w-4 text-amber-500/60" /></div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">Start your streak today</p>
                    <p className="text-[11px] text-muted-foreground">Complete a daily lesson to earn XP</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-amber-500/60" />
                </div>
              </Link>
            )
          ) : (
            <Link href="/learning" className="block rounded-2xl border border-dashed border-amber-500/20 bg-gradient-to-br from-amber-500/5 to-orange-500/5 p-4 hover:border-amber-500/40 hover:-translate-y-0.5 transition-all duration-300">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10"><Flame className="h-4 w-4 text-amber-500/60" /></div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">Daily Learn</p>
                  <p className="text-[11px] text-muted-foreground">Sharpen skills · earn XP · build streaks</p>
                </div>
                <ArrowRight className="h-4 w-4 text-amber-500/60" />
              </div>
            </Link>
          )}
        </div>
      </div>

      {/* Delete dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle>Delete workspace</DialogTitle>
            <DialogDescription>Delete &ldquo;{deleteTarget?.title}&rdquo;? This removes all documents and history.</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" className="rounded-xl" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
            <Button variant="destructive" className="rounded-xl gap-2" onClick={handleDelete}>{deleting ? "Deleting..." : "Delete"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Achievement unlock notification */}
      <AchievementToast
        achievement={pendingAchievement}
        onDismiss={() => setPendingAchievement(null)}
      />
    </div>
  );
}
