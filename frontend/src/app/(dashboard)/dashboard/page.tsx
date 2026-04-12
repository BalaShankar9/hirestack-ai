"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight, Sparkles, Clock, Target, ShieldCheck, ScanEye, Award,
  Plus, Briefcase, TrendingUp, Trash2, Zap, FileSearch, MessageSquare,
  DollarSign, BookOpen, BarChart3, Brain, Flame,
  Bot, Activity, CheckCircle2, User,
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
    <div className="relative" style={{ width: 120, height: 120 }}>
      <svg width={120} height={120} className="-rotate-90">
        <circle cx={60} cy={60} r={r} strokeWidth={8} fill="none" className="stroke-white/10" />
        <circle cx={60} cy={60} r={r} strokeWidth={8} fill="none" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          className={cn("transition-all duration-1000 ease-out", color)} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold tabular-nums text-white">{value}</span>
        <span className="text-[9px] text-white/50 uppercase tracking-widest">Career Pulse</span>
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
] as const;

/* ── Page ─────────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const router = useRouter();
  const { user, session: authSession } = useAuth();
  const userId = user?.uid || user?.id || null;

  const { data: apps = [], loading: appsLoading, removeItem: removeApp } = useApplications(userId, 50);
  const { data: tasks = [], loading: tasksLoading } = useTasks(userId, null, 200);
  const { data: evidence = [], loading: evidenceLoading } = useEvidence(userId, 200);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [briefing, setBriefing] = useState<any>(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [streak, setStreak] = useState<{ current_streak: number; longest_streak: number; total_points: number; level: number } | null>(null);

  const openTasks = useMemo(() => tasks.filter((t) => t.status === "todo"), [tasks]);
  const topApps = useMemo(() => apps.slice(0, 8), [apps]);

  const stats = useMemo(() => {
    const active = apps.filter((a) => a.status !== "archived").length;
    const avgMatch = apps.length === 0 ? 0 : Math.round(apps.reduce((s, a) => s + (a.scores?.match ?? 0), 0) / apps.length);
    // Career Pulse: weighted health score
    const completeness = Math.min(100, active * 15);
    const matchHealth = avgMatch;
    const evidenceHealth = Math.min(100, evidence.length * 12);
    const taskHealth = openTasks.length > 0 ? Math.max(0, 100 - openTasks.length * 8) : 100;
    const pulse = Math.round(completeness * 0.2 + matchHealth * 0.4 + evidenceHealth * 0.2 + taskHealth * 0.2);
    return { apps: active, openTasks: openTasks.length, evidence: evidence.length, avgMatch, pulse };
  }, [apps, evidence.length, openTasks.length]);

  // Load AI briefing
  useEffect(() => {
    if (!userId || briefing) return;
    const token = authSession?.access_token;
    if (!token) return;
    setBriefingLoading(true);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
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
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    fetch(`${API_URL}/api/learning/streak`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setStreak(d))
      .catch(() => {});
  }, [userId, authSession?.access_token]);

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
        hasEvidence: evidence.length > 0,
      });
    }
  }, [apps.length, evidence.length, appsLoading, evidenceLoading, updateCounts]);

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
          className="rounded-3xl border bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-8 text-white shadow-glow-md overflow-hidden relative"
        >
          <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "24px 24px" }} />
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
                done: false,
                href: "/new",
              },
              {
                step: 2,
                title: "Add your resume or profile",
                desc: "Upload a resume or set up your profile so documents are tailored to your experience.",
                done: false,
                href: "/nexus",
              },
              {
                step: 3,
                title: "Review your application workspace",
                desc: "Get fit analysis, tailored documents, gap report, and evidence suggestions.",
                done: false,
                href: null,
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
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { icon: Target, label: "Fit Analysis", desc: "Match score vs job requirements", color: "text-emerald-500 bg-emerald-500/10" },
              { icon: FileSearch, label: "ATS Optimization", desc: "Keyword coverage & format fixes", color: "text-blue-500 bg-blue-500/10" },
              { icon: ShieldCheck, label: "Evidence Mapping", desc: "Proof attached to every claim", color: "text-violet-500 bg-violet-500/10" },
              { icon: Briefcase, label: "Tailored Documents", desc: "CV, cover letter & more", color: "text-primary bg-primary/10" },
              { icon: TrendingUp, label: "Gap Report", desc: "What to improve before applying", color: "text-amber-500 bg-amber-500/10" },
              { icon: MessageSquare, label: "Interview Prep", desc: "Predicted questions & answers", color: "text-rose-500 bg-rose-500/10" },
            ].map((item) => (
              <div key={item.label} className="flex items-start gap-3 rounded-xl bg-muted/20 p-3">
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
        className="rounded-3xl border bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-6 text-white shadow-glow-md overflow-hidden relative"
      >
        {/* Decorative grid */}
        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

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
            <div key={s.label} className={cn("rounded-xl border border-white/10 bg-white/10 p-3 backdrop-blur-sm", s.accent && "border-white/20 bg-white/15")}>
              <div className="flex items-center gap-1.5 text-[10px] text-white/50">
                <s.icon className="h-3 w-3" /> {s.label}
              </div>
              <div className="mt-0.5 text-xl font-bold tabular-nums">{s.value}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ── Quick Actions ─────────────────────────────────────── */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        {QUICK_ACTIONS.map((a, i) => (
          <motion.div
            key={a.href}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.05 }}
          >
            <Link href={a.href} className="group flex flex-col items-center gap-2 rounded-xl border bg-card p-3 hover:border-primary/20 hover:shadow-soft-sm transition-all">
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
        <div className="space-y-4">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-lg font-semibold">Applications</h2>
              <p className="text-xs text-muted-foreground">Your active application workspaces</p>
            </div>
            {topApps.length > 0 && (
              <Button variant="outline" size="sm" className="gap-1.5 rounded-xl text-xs" onClick={() => router.push("/new")}>
                <Plus className="h-3 w-3" /> New
              </Button>
            )}
          </div>

          {appsLoading ? (
            <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
          ) : topApps.length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
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
                  <div key={a.id} className="group relative rounded-2xl border bg-card p-4 shadow-soft-sm hover:shadow-soft-md hover:border-primary/20 transition-all">
                    <button type="button" onClick={(e) => { e.preventDefault(); setDeleteTarget({ id: a.id, title }); }}
                      className="absolute right-3 top-3 z-10 h-6 w-6 flex items-center justify-center rounded-lg opacity-0 group-hover:opacity-100 hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all">
                      <Trash2 className="h-3 w-3" />
                    </button>
                    <Link href={`/applications/${a.id}`} className="block">
                      <div className="flex items-start justify-between gap-2 pr-6">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold truncate group-hover:text-primary transition-colors">{title}</p>
                          {company && <p className="text-xs text-muted-foreground truncate mt-0.5">{company}</p>}
                        </div>
                        <Badge className={cn("border text-[11px] shrink-0 tabular-nums",
                          match >= 80 ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                          match >= 60 ? "bg-blue-500/10 text-blue-500 border-blue-500/20" :
                          match >= 40 ? "bg-amber-500/10 text-amber-500 border-amber-500/20" :
                          "bg-rose-500/10 text-rose-500 border-rose-500/20"
                        )} variant="secondary">{match}%</Badge>
                      </div>
                      <div className="mt-2.5 h-1 rounded-full bg-muted overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all", scoreBg(match))} style={{ width: `${match}%` }} />
                      </div>
                      <div className="mt-2 grid grid-cols-4 gap-1.5">
                        {[
                          { icon: Target, label: "Match", val: match },
                          { icon: ShieldCheck, label: "ATS", val: a.scores?.atsReadiness ?? 0 },
                          { icon: ScanEye, label: "Scan", val: a.scores?.recruiterScan ?? 0 },
                          { icon: Award, label: "Proof", val: proof },
                        ].map((m) => (
                          <div key={m.label} className="rounded-md bg-muted/30 p-1.5 text-center">
                            <div className="flex items-center justify-center gap-0.5 text-muted-foreground"><m.icon className="h-2.5 w-2.5" /><span className="text-[9px]">{m.label}</span></div>
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
          {apps.length > 8 && <div className="text-center"><Button variant="ghost" size="sm" className="text-xs text-muted-foreground">View all {apps.length}</Button></div>}
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          <TaskQueue tasks={openTasks.slice(0, 12)} onOpenWorkspace={(id) => router.push(`/applications/${id}`)}
            onToggle={async (t) => { try { await setTaskStatus(userId!, t.id, t.status === "done" ? "todo" : "done"); } catch {} }} compact />

          <Link href="/evidence" className="block rounded-2xl border bg-card p-4 hover:border-violet-500/20 hover:shadow-soft-sm transition-all">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10"><ShieldCheck className="h-4 w-4 text-violet-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Evidence</p><p className="text-[11px] text-muted-foreground">{evidence.length} proof items collected</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          <Link href="/nexus" className="block rounded-2xl border bg-card p-4 hover:border-teal-500/20 hover:shadow-soft-sm transition-all">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-500/10"><User className="h-4 w-4 text-teal-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Profile</p><p className="text-[11px] text-muted-foreground">Your career identity & resume</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          <Link href="/career-analytics" className="block rounded-2xl border bg-card p-4 hover:border-blue-500/20 hover:shadow-soft-sm transition-all">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10"><BarChart3 className="h-4 w-4 text-blue-500" /></div>
              <div className="flex-1"><p className="text-sm font-semibold">Progress</p><p className="text-[11px] text-muted-foreground">Track readiness over time</p></div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>

          {/* Learning Streak */}
          {streak && (streak.current_streak > 0 || streak.total_points > 0) && (
            <Link href="/learning" className="block rounded-2xl border bg-gradient-to-br from-amber-500/5 to-orange-500/5 p-4 hover:border-amber-500/20 hover:shadow-soft-sm transition-all">
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
    </div>
  );
}
