"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BookOpen, GraduationCap, Sparkles } from "lucide-react";

import { useAuth } from "@/components/providers";
import { useApplications, useTasks } from "@/lib/firestore";
import { setTaskStatus, trackEvent } from "@/lib/firestore";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskQueue } from "@/components/workspace/task-queue";

export default function CareerLabPage() {
  const router = useRouter();
  const { user } = useAuth();

  const { data: apps = [], loading: appsLoading } = useApplications(user?.uid || null, 50);
  const { data: tasks = [], loading: tasksLoading } = useTasks(user?.uid || null, null, 300);

  const learningTasks = useMemo(
    () => tasks.filter((t) => t.source === "learningPlan"),
    [tasks]
  );

  const todoLearning = useMemo(
    () => learningTasks.filter((t) => t.status === "todo"),
    [learningTasks]
  );

  const latestPlan = useMemo(() => {
    const active = apps.filter((a) => a.status === "active" && a.learningPlan);
    return active[0]?.learningPlan || null;
  }, [apps]);

  if (!user) return null;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-violet-600 text-white flex items-center justify-center">
                <GraduationCap className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-semibold">Career Lab</div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Skill sprints built from your gaps — produce proof, not vibes.
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => router.push("/new")} className="gap-2 rounded-xl">
              New application <ArrowRight className="h-4 w-4" />
            </Button>
            <Button variant="outline" onClick={() => router.push("/evidence")} className="gap-2 rounded-xl">
              Evidence vault <Sparkles className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <Separator className="my-4" />

        <div className="grid gap-3 md:grid-cols-3">
          <Stat label="Learning tasks" value={learningTasks.length} loading={tasksLoading} />
          <Stat label="Open sprints" value={todoLearning.length} loading={tasksLoading} />
          <Stat label="Active workspaces" value={apps.filter((a) => a.status === "active").length} loading={appsLoading} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-y-4">
          <TaskQueue
            tasks={todoLearning.slice(0, 16)}
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
          />
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              <div className="text-sm font-semibold">Resources</div>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Pulled from your latest learning plan. Build proof artifacts as you learn.
            </div>
            <Separator className="my-4" />

            {!latestPlan ? (
              <div className="rounded-xl bg-muted/40 p-4">
                <div className="text-sm font-medium">No learning plan yet.</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Generate a learning plan inside a workspace to populate this hub.
                </div>
                <div className="mt-3">
                  <Button variant="outline" size="sm" onClick={() => router.push("/new")}>
                    Start wizard
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {(latestPlan.resources ?? []).map((r) => (
                  <div key={String(r.title ?? "")} className="rounded-xl border p-3">
                    <div className="text-sm font-semibold">{String(r.title ?? "")}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {String(r.provider || "Resource")} · {String(r.timebox || "Timebox")} {r.skill ? `· ${String(r.skill)}` : ""}
                    </div>
                    {r.url ? (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex text-xs text-blue-700 hover:underline"
                      >
                        Open link
                      </a>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5">
            <div className="text-sm font-semibold text-primary">Coach principle</div>
            <div className="mt-1 text-xs text-muted-foreground leading-snug">
              Your goal is not “learning”. Your goal is shipping proof. Every sprint should end with an artifact you can attach to your Evidence Vault.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, loading }: { label: string; value: number; loading: boolean }) {
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">
        {loading ? <Skeleton className="h-7 w-16" /> : value}
      </div>
    </div>
  );
}

