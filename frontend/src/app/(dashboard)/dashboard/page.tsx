"use client";

import { useMemo, useState } from "react";
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
  Trash2,
  Zap,
  FileSearch,
  MessageSquare,
  DollarSign,
  BookOpen,
  FlaskConical,
  BarChart3,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import { computeEvidenceStrengthScore, useApplications, useEvidence, useTasks } from "@/lib/firestore";
import { deleteApplication, setTaskStatus, trackEvent } from "@/lib/firestore";
import { toast } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TaskQueue } from "@/components/workspace/task-queue";
import { cn } from "@/lib/utils";

/* ── Helpers ──────────────────────────────────────────────────────── */

function formatRelativeTime(timestamp: number | string): string {
  try {
    const date = typeof timestamp === "string" ? new Date(timestamp) : new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "Recently";
  }
}

function scoreLabel(score: number) {
  if (score >= 80) return "Excellent";
  if (score >= 60) return "Strong";
  if (score >= 40) return "Developing";
  return "Needs work";
}

function scoreTint(score: number) {
  if (score >= 80) return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800";
  if (score >= 60) return "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800";
  if (score >= 40) return "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800";
  return "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800";
}

function metricColor(value: number) {
  if (value >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (value >= 60) return "text-blue-600 dark:text-blue-400";
  if (value >= 40) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/* ── Quick Actions ────────────────────────────────────────────────── */

const QUICK_ACTIONS = [
  { href: "/new", label: "New Application", icon: Plus, color: "bg-primary/10 text-primary" },
  { href: "/ats-scanner", label: "ATS Scan", icon: FileSearch, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { href: "/interview", label: "Interview Prep", icon: MessageSquare, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  { href: "/salary", label: "Salary Coach", icon: DollarSign, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { href: "/learning", label: "Daily Learn", icon: BookOpen, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { href: "/ab-lab", label: "A/B Lab", icon: FlaskConical, color: "bg-rose-500/10 text-rose-600 dark:text-rose-400" },
] as const;

/* ── Page ─────────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();

  const userId = user?.uid || user?.id || null;
  const { data: apps = [], loading: appsLoading, removeItem: removeApp } = useApplications(userId, 50);
  const { data: tasks = [], loading: tasksLoading } = useTasks(userId, null, 200);
  const { data: evidence = [], loading: evidenceLoading } = useEvidence(userId, 200);

  const topApps = useMemo(() => apps.slice(0, 8), [apps]);

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!deleteTarget || !userId) return;
    setDeleting(true);
    try {
      await deleteApplication(deleteTarget.id);
      removeApp(deleteTarget.id);
      await trackEvent(userId, { name: "app_deleted", appId: deleteTarget.id });
      toast.success("Workspace deleted", `"${deleteTarget.title}" has been removed.`);
    } catch (err: any) {
      toast.error("Delete failed", err?.message ?? "Something went wrong.");
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

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

  const userName = user?.user_metadata?.full_name || user?.full_name || user?.email?.split("@")[0] || "";

  return (
    <div className="space-y-6">
      {/* ── Hero ──────────────────────────────────────────────── */}
      <div className="rounded-3xl border bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-6 text-white shadow-soft-lg">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <h1 className="text-2xl md:text-3xl font-semibold leading-tight">
              {greeting()}{userName ? `, ${userName}` : ""}
            </h1>
            <p className="mt-2 text-sm text-white/70 leading-relaxed">
              {stats.apps === 0
                ? "Start your first application to unlock AI-powered benchmarks, gap analysis, and tailored documents."
                : stats.openTasks > 0
                  ? `You have ${stats.openTasks} open task${stats.openTasks > 1 ? "s" : ""} across ${stats.apps} workspace${stats.apps > 1 ? "s" : ""}. Keep building proof.`
                  : `${stats.apps} active workspace${stats.apps > 1 ? "s" : ""} with ${stats.avgMatch}% average match. Looking strong.`}
            </p>
          </div>
          <Button
            className="bg-white text-primary hover:bg-white/90 shadow-soft-sm shrink-0"
            onClick={() => router.push("/new")}
          >
            New application
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>

        <div className="mt-6 grid gap-3 grid-cols-2 md:grid-cols-4">
          <StatCard icon={<Briefcase className="h-3.5 w-3.5" />} label="Active workspaces" value={stats.apps} />
          <StatCard icon={<Zap className="h-3.5 w-3.5" />} label="Open tasks" value={stats.openTasks} accent={stats.openTasks > 0} />
          <StatCard icon={<ShieldCheck className="h-3.5 w-3.5" />} label="Evidence items" value={stats.evidence} />
          <StatCard icon={<TrendingUp className="h-3.5 w-3.5" />} label="Avg match" value={`${stats.avgMatch}%`} />
        </div>
      </div>

      {/* ── Quick Actions ─────────────────────────────────────── */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Quick Actions</h2>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
          {QUICK_ACTIONS.map((action) => (
            <Link
              key={action.href}
              href={action.href}
              className="group flex flex-col items-center gap-2 rounded-xl border bg-card p-3 hover:border-primary/20 hover:shadow-soft-sm transition-all duration-200"
            >
              <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg transition-transform group-hover:scale-110", action.color)}>
                <action.icon className="h-4 w-4" />
              </div>
              <span className="text-[11px] font-medium text-muted-foreground group-hover:text-foreground transition-colors text-center leading-tight">
                {action.label}
              </span>
            </Link>
          ))}
        </div>
      </div>

      {/* ── Main Grid ─────────────────────────────────────────── */}
      <div className="grid gap-8 lg:grid-cols-[1fr_380px]">
        {/* Left: Workspaces */}
        <div className="space-y-4">
          <div className="flex items-end justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Workspaces</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Each workspace contains benchmark, gaps, learning plan, and tailored documents.
              </p>
            </div>
            {topApps.length > 0 && (
              <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => router.push("/new")}>
                <Plus className="h-3.5 w-3.5" />
                New
              </Button>
            )}
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
            <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                <Briefcase className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mt-4 text-sm font-semibold">No applications yet</h3>
              <p className="mt-1 text-xs text-muted-foreground max-w-sm mx-auto">
                Paste a job description, upload your resume, and let the AI generate a complete application workspace.
              </p>
              <Button className="mt-5 gap-2 rounded-xl" onClick={() => router.push("/new")}>
                Start your first application <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {topApps.map((a) => {
                const appTitle = a.title || a.confirmedFacts?.jobTitle || "Untitled application";
                const company = a.confirmedFacts?.company;
                const proofScore = Array.isArray(a.benchmark?.keywords) && a.benchmark!.keywords.length > 0
                  ? computeEvidenceStrengthScore({ evidence, keywords: a.benchmark!.keywords })
                  : (a.scores?.evidenceStrength ?? 0);
                const matchScore = a.scores?.match ?? 0;

                return (
                  <div
                    key={a.id}
                    className="group relative rounded-2xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md hover:border-primary/20 transition-all duration-300"
                  >
                    {/* Delete */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setDeleteTarget({ id: a.id, title: appTitle });
                      }}
                      className="absolute right-3 top-3 z-10 flex h-7 w-7 items-center justify-center rounded-lg bg-transparent opacity-0 group-hover:opacity-100 hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all duration-200"
                      title="Delete workspace"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>

                    <Link href={`/applications/${a.id}`} className="block">
                      {/* Header */}
                      <div className="flex items-start justify-between gap-2 pr-6">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold truncate group-hover:text-primary transition-colors">
                            {appTitle}
                          </div>
                          {company && (
                            <div className="mt-0.5 text-xs text-muted-foreground truncate">{company}</div>
                          )}
                        </div>
                        <Badge className={cn("border text-[11px] shrink-0", scoreTint(matchScore))} variant="secondary">
                          {matchScore}%
                        </Badge>
                      </div>

                      {/* Score bar */}
                      <div className="mt-3 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all duration-500", matchScore >= 70 ? "bg-emerald-500" : matchScore >= 40 ? "bg-amber-500" : "bg-rose-500")}
                          style={{ width: `${matchScore}%` }}
                        />
                      </div>

                      {/* Mini metrics */}
                      <div className="mt-3 grid grid-cols-4 gap-2">
                        <MiniMetric icon={<Target className="h-3 w-3" />} label="Match" value={a.scores?.match ?? 0} />
                        <MiniMetric icon={<ShieldCheck className="h-3 w-3" />} label="ATS" value={a.scores?.atsReadiness ?? 0} />
                        <MiniMetric icon={<ScanEye className="h-3 w-3" />} label="Scan" value={a.scores?.recruiterScan ?? 0} />
                        <MiniMetric icon={<Award className="h-3 w-3" />} label="Proof" value={proofScore} />
                      </div>

                      {/* Footer */}
                      <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatRelativeTime(a.updatedAt)}
                        </span>
                        <span className={cn("font-medium", metricColor(matchScore))}>
                          {scoreLabel(matchScore)}
                        </span>
                      </div>
                    </Link>
                  </div>
                );
              })}
            </div>
          )}

          {/* Show all link */}
          {apps.length > 8 && (
            <div className="text-center">
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
                View all {apps.length} workspaces
              </Button>
            </div>
          )}

          {/* Delete dialog */}
          <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
            <DialogContent className="sm:max-w-md rounded-2xl">
              <DialogHeader>
                <DialogTitle>Delete workspace</DialogTitle>
                <DialogDescription>
                  Are you sure you want to delete <span className="font-medium text-foreground">&ldquo;{deleteTarget?.title}&rdquo;</span>?
                  This will permanently remove all documents, benchmarks, and history.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button variant="outline" className="rounded-xl" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                  Cancel
                </Button>
                <Button variant="destructive" className="rounded-xl gap-2" onClick={handleDelete} loading={deleting}>
                  <Trash2 className="h-4 w-4" />
                  {deleting ? "Deleting…" : "Delete"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Task queue */}
          <TaskQueue
            tasks={openTasks.slice(0, 12)}
            onOpenWorkspace={(appId) => router.push(`/applications/${appId}`)}
            onToggle={async (task) => {
              try {
                const next = task.status === "done" ? "todo" : "done";
                await setTaskStatus(userId!, task.id, next);
                if (next === "done") {
                  await trackEvent(userId!, { name: "task_completed", appId: task.appId ?? undefined, properties: { taskId: task.id } });
                }
              } catch (err) {
                console.error("Task toggle failed:", err);
              }
            }}
            compact
          />

          {/* Evidence Pulse */}
          <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10">
                <ShieldCheck className="h-4 w-4 text-violet-600 dark:text-violet-400" />
              </div>
              <div>
                <div className="text-sm font-semibold">Evidence Vault</div>
                <div className="text-[11px] text-muted-foreground">
                  2–3 proof items per critical keyword.
                </div>
              </div>
            </div>
            <Separator className="my-3" />
            <div className="flex items-center justify-between">
              {evidenceLoading ? (
                <Skeleton className="h-6 w-24" />
              ) : (
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-bold tabular-nums">{evidence.length}</span>
                  <span className="text-xs text-muted-foreground">items collected</span>
                </div>
              )}
              <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => router.push("/evidence")}>
                Open vault
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Analytics shortcut */}
          <Link href="/career-analytics" className="block rounded-2xl border bg-card p-5 shadow-soft-sm hover:border-primary/20 hover:shadow-soft-md transition-all duration-200">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10">
                <BarChart3 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold">Career Analytics</div>
                <div className="text-[11px] text-muted-foreground">
                  Track your score progression over time
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────── */

function StatCard({
  icon,
  label,
  value,
  accent = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className={cn(
      "rounded-xl border border-white/10 bg-white/10 p-3.5 backdrop-blur-sm",
      accent && "border-white/20 bg-white/15"
    )}>
      <div className="flex items-center gap-1.5 text-[11px] text-white/60">
        {icon}
        {label}
      </div>
      <div className={cn("mt-1 text-2xl font-bold tabular-nums", accent && "text-white")}>{value}</div>
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
      <div className={cn("mt-0.5 text-xs font-semibold tabular-nums", metricColor(value))}>{value}%</div>
    </div>
  );
}
