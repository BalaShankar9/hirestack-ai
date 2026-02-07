"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Sparkles,
  Clock,
  Target,
  ShieldCheck,
  ScanEye,
  Award,
  Plus,
  Briefcase,
  TrendingUp,
  Zap,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import { useApplications, useEvidence, useTasks } from "@/lib/firestore";
import { setTaskStatus, trackEvent } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskQueue } from "@/components/workspace/task-queue";
import { cn } from "@/lib/utils";

function formatTime(ms: number) {
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(ms);
  }
}

function scoreLabel(score: number) {
  if (score >= 80) return "Excellent";
  if (score >= 60) return "Strong";
  if (score >= 40) return "Developing";
  return "Needs work";
}

function scoreTint(score: number) {
  if (score >= 80) return "bg-emerald-500/10 text-emerald-700 border-emerald-200";
  if (score >= 60) return "bg-blue-500/10 text-blue-700 border-blue-200";
  if (score >= 40) return "bg-amber-500/10 text-amber-700 border-amber-200";
  return "bg-rose-500/10 text-rose-700 border-rose-200";
}

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();

  const { data: apps = [], loading: appsLoading } = useApplications(user?.uid || null, 50);
  const { data: tasks = [], loading: tasksLoading } = useTasks(user?.uid || null, null, 200);
  const { data: evidence = [], loading: evidenceLoading } = useEvidence(user?.uid || null, 200);

  const topApps = useMemo(() => apps.slice(0, 8), [apps]);
  const openTasks = useMemo(() => tasks.filter((t) => t.status === "todo"), [tasks]);

  const stats = useMemo(() => {
    const active = apps.filter((a) => a.status !== "archived").length;
    const avgMatch =
      apps.length === 0
        ? 0
        : Math.round(
            apps.reduce((sum, a) => sum + (a.scores?.match ?? a.scores?.overall ?? 0), 0) / apps.length
          );
    return {
      apps: active,
      openTasks: openTasks.length,
      evidence: evidence.length,
      avgMatch,
    };
  }, [apps, evidence.length, openTasks.length]);

  if (!user) return null;

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="rounded-3xl border bg-gradient-to-br from-blue-600 to-indigo-700 p-6 text-white">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium">
              <Sparkles className="h-4 w-4" />
              Application intelligence workspace
            </div>
            <h1 className="mt-3 text-2xl md:text-3xl font-semibold leading-tight">
              Diagnose → plan → build proof → ship → track
            </h1>
            <p className="mt-2 text-sm text-blue-100 leading-relaxed">
              This isn’t “upload and output”. It’s an iterative system: lock facts, target the JD, generate explainable
              modules, and keep a coach-grade action queue.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              className="bg-white text-blue-700 hover:bg-blue-50"
              onClick={() => router.push("/new")}
            >
              New application
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="border-white/30 text-white hover:bg-white/10"
              onClick={() => router.push("/evidence")}
            >
              Evidence vault
            </Button>
          </div>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-4">
          <StatCard icon={<Briefcase className="h-3.5 w-3.5" />} label="Active workspaces" value={stats.apps} />
          <StatCard icon={<Zap className="h-3.5 w-3.5" />} label="Open tasks" value={stats.openTasks} />
          <StatCard icon={<Sparkles className="h-3.5 w-3.5" />} label="Evidence items" value={stats.evidence} />
          <StatCard icon={<TrendingUp className="h-3.5 w-3.5" />} label="Avg match" value={`${stats.avgMatch}%`} />
        </div>
      </div>

      {/* ── Main Grid ────────────────────────────────── */}
      <div className="grid gap-8 lg:grid-cols-[1fr_400px]">
        {/* Left: Workspaces */}
        <div className="space-y-5">
          <div className="flex items-end justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Your Workspaces</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Each workspace contains benchmark, gaps, learning plan, docs, and a coach queue.
              </p>
            </div>
            <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => router.push("/new")}>
              <Plus className="h-3.5 w-3.5" />
              New
            </Button>
          </div>

          {appsLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="rounded-2xl border bg-card p-5">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="mt-3 h-4 w-1/2" />
                  <Skeleton className="mt-5 h-12 w-full rounded-xl" />
                </div>
              ))}
            </div>
          ) : topApps.length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-card/50 p-8 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                <Briefcase className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mt-4 text-sm font-semibold">No applications yet</h3>
              <p className="mt-1 text-xs text-muted-foreground max-w-sm mx-auto">
                Start a workspace, lock facts, paste the JD, and generate modules with a progress stepper.
              </p>
              <Button className="mt-5 gap-2 rounded-xl" onClick={() => router.push("/new")}>
                Start the wizard <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 animate-stagger">
              {topApps.map((a) => (
                <Link
                  key={a.id}
                  href={`/applications/${a.id}`}
                  className="group rounded-2xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md hover:border-primary/20 transition-all duration-300"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold truncate group-hover:text-primary transition-colors">
                        {a.title || a.confirmedFacts?.jobTitle || "Untitled application"}
                      </div>
                      {a.confirmedFacts?.company && (
                        <div className="mt-0.5 text-xs text-muted-foreground">{a.confirmedFacts.company}</div>
                      )}
                      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        Updated {formatTime(a.updatedAt)}
                      </div>
                    </div>
                    <Badge className={cn("border text-[11px] shrink-0", scoreTint(a.scores?.match ?? 0))} variant="secondary">
                      {a.scores?.match ?? 0}% · {scoreLabel(a.scores?.match ?? 0)}
                    </Badge>
                  </div>

                  {/* Mini metrics */}
                  <div className="mt-4 grid grid-cols-4 gap-2">
                    <MiniMetric icon={<Target className="h-3 w-3" />} label="Match" value={a.scores?.match ?? 0} />
                    <MiniMetric icon={<ShieldCheck className="h-3 w-3" />} label="ATS" value={a.scores?.atsReadiness ?? 0} />
                    <MiniMetric icon={<ScanEye className="h-3 w-3" />} label="Scan" value={a.scores?.recruiterScan ?? 0} />
                    <MiniMetric icon={<Award className="h-3 w-3" />} label="Proof" value={a.scores?.evidenceStrength ?? 0} />
                  </div>

                  {/* Top fix */}
                  <div className="mt-4 rounded-xl bg-primary/5 border border-primary/10 p-3">
                    <div className="text-[11px] font-semibold text-primary">Top fix</div>
                    <div className="mt-1 text-xs text-muted-foreground leading-snug">
                      {typeof a.scores?.topFix === "string" ? a.scores.topFix : "Generate modules to get your first coach fix."}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Right: Task queue + evidence */}
        <div className="space-y-5">
          <TaskQueue
            tasks={openTasks.slice(0, 12)}
            onOpenWorkspace={(appId) => router.push(`/applications/${appId}`)}
            onToggle={async (task) => {
              try {
                const next = task.status === "done" ? "todo" : "done";
                await setTaskStatus(user.uid, task.id, next);
                if (next === "done") {
                  await trackEvent(user.uid, { name: "task_completed", appId: task.appId ?? undefined, properties: { taskId: task.id } });
                }
              } catch (err) {
                console.error("Task toggle failed:", err);
              }
            }}
            compact
          />

          <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10">
                <ShieldCheck className="h-4 w-4 text-violet-600" />
              </div>
              <div>
                <div className="text-sm font-semibold">Evidence Pulse</div>
                <div className="text-[11px] text-muted-foreground">
                  Aim for 2–3 proof items per critical keyword.
                </div>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              {evidenceLoading ? (
                <Skeleton className="h-6 w-24" />
              ) : (
                <Badge variant="secondary" className="tabular-nums rounded-lg">
                  {evidence.length} items
                </Badge>
              )}
              <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => router.push("/evidence")}>
                Open vault
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/10 p-4 backdrop-blur-sm">
      <div className="flex items-center gap-2 text-[11px] text-white/60">
        {icon}
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function MiniMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-lg border bg-muted/30 p-2 text-center">
      <div className="flex items-center justify-center gap-1 text-muted-foreground">
        {icon}
        <span className="text-[10px]">{label}</span>
      </div>
      <div className="mt-0.5 text-xs font-semibold tabular-nums">{value}%</div>
    </div>
  );
}

