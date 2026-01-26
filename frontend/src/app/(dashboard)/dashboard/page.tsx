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
} from "lucide-react";

import { useAuth } from "@/components/providers";
import { useApplications, useEvidence, useTasks } from "@/lib/firestore";
import { setTaskStatus, trackEvent } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskQueue } from "@/components/workspace/task-queue";

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
  if (score >= 80) return "bg-green-50 text-green-800 border-green-200";
  if (score >= 60) return "bg-blue-50 text-blue-800 border-blue-200";
  if (score >= 40) return "bg-amber-50 text-amber-900 border-amber-200";
  return "bg-red-50 text-red-800 border-red-200";
}

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();

  const { data: apps, loading: appsLoading } = useApplications(user?.uid || null, 50);
  const { data: tasks, loading: tasksLoading } = useTasks(user?.uid || null, null, 200);
  const { data: evidence, loading: evidenceLoading } = useEvidence(user?.uid || null, 200);

  const topApps = useMemo(() => apps.slice(0, 8), [apps]);
  const openTasks = useMemo(() => tasks.filter((t) => t.status === "todo"), [tasks]);

  const stats = useMemo(() => {
    const active = apps.filter((a) => a.status !== "archived").length;
    const avgMatch =
      apps.length === 0
        ? 0
        : Math.round(
            apps.reduce((sum, a) => sum + (a.scores?.match || 0), 0) / apps.length
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
          <Stat label="Active workspaces" value={stats.apps} />
          <Stat label="Open tasks" value={stats.openTasks} />
          <Stat label="Evidence items" value={stats.evidence} />
          <Stat label="Avg match" value={`${stats.avgMatch}%`} />
        </div>
      </div>

      {/* Workspaces */}
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-y-4">
          <div className="flex items-end justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">Your workspaces</div>
              <div className="text-xs text-muted-foreground">
                Each workspace contains benchmark, gaps, learning plan, docs, and a coach queue.
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => router.push("/new")}>
              New application
            </Button>
          </div>

          {appsLoading ? (
            <div className="grid gap-3 md:grid-cols-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-2xl border bg-white p-4">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="mt-2 h-4 w-1/2" />
                  <Skeleton className="mt-4 h-10 w-full" />
                </div>
              ))}
            </div>
          ) : topApps.length === 0 ? (
            <div className="rounded-2xl border bg-white p-6">
              <div className="text-sm font-semibold">No applications yet.</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Start a workspace, lock facts, paste the JD, and generate modules with a progress stepper.
              </div>
              <div className="mt-4">
                <Button onClick={() => router.push("/new")}>
                  Start the wizard <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {topApps.map((a) => (
                <Link
                  key={a.id}
                  href={`/applications/${a.id}`}
                  className="rounded-2xl border bg-white p-4 hover:shadow-sm hover:border-blue-200 transition-all"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate">
                        {a.job.title || "Untitled application"}
                        {a.job.company ? <span className="text-muted-foreground"> · {a.job.company}</span> : null}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        Updated {formatTime(a.updatedAt)}
                      </div>
                    </div>
                    <Badge className={`border ${scoreTint(a.scores.match)}`} variant="secondary">
                      {a.scores.match}% · {scoreLabel(a.scores.match)}
                    </Badge>
                  </div>

                  <div className="mt-4 grid grid-cols-4 gap-2 text-[11px] text-muted-foreground">
                    <MiniMetric icon={<Target className="h-3.5 w-3.5" />} label="Match" value={a.scores.match} />
                    <MiniMetric icon={<ShieldCheck className="h-3.5 w-3.5" />} label="ATS" value={a.scores.atsReadiness} />
                    <MiniMetric icon={<ScanEye className="h-3.5 w-3.5" />} label="Scan" value={a.scores.recruiterScan} />
                    <MiniMetric icon={<Award className="h-3.5 w-3.5" />} label="Evidence" value={a.scores.evidenceStrength} />
                  </div>

                  <div className="mt-4 rounded-xl bg-blue-50 p-3">
                    <div className="text-[11px] font-semibold text-blue-900">Top fix</div>
                    <div className="mt-1 text-xs text-blue-900/80 leading-snug">
                      {a.scores.topFix}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <TaskQueue
            tasks={openTasks.slice(0, 12)}
            onOpenWorkspace={(appId) => router.push(`/applications/${appId}`)}
            onToggle={async (task) => {
              const next = task.status === "done" ? "todo" : "done";
              await setTaskStatus(user.uid, task.id, next);
              if (next === "done") {
                await trackEvent(user.uid, { name: "task_completed", appId: task.appId, properties: { taskId: task.id } });
              }
            }}
            compact
          />

          <div className="rounded-2xl border bg-white p-5">
            <div className="text-sm font-semibold">Evidence pulse</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Evidence boosts credibility. Aim for 2–3 proof items per critical keyword.
            </div>
            <div className="mt-4 flex items-center justify-between">
              {evidenceLoading ? (
                <Skeleton className="h-6 w-24" />
              ) : (
                <Badge variant="secondary" className="tabular-nums">
                  {evidence.length} items
                </Badge>
              )}
              <Button variant="outline" size="sm" onClick={() => router.push("/evidence")}>
                Open vault
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-white/15 bg-white/10 p-4">
      <div className="text-xs text-blue-100">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function MiniMetric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border bg-white p-2">
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1 min-w-0">
          <div className="text-muted-foreground">{icon}</div>
          <div className="truncate">{label}</div>
        </div>
        <div className="font-medium tabular-nums text-foreground">{value}%</div>
      </div>
    </div>
  );
}

