"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/** Safely coerce any DB value to a renderable string — handles both
 *  plain strings and legacy object shapes (e.g. {dimension, indicators}). */
function toLabel(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") {
    // pick the first string-valued key we find
    const obj = v as Record<string, unknown>;
    for (const k of ["dimension", "title", "name", "area", "description", "gap", "suggestion", "label"]) {
      if (typeof obj[k] === "string") return obj[k] as string;
    }
    return JSON.stringify(v);
  }
  return String(v ?? fallback);
}
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  FileText,
  GraduationCap,
  Layers,
  RefreshCw,
  Sparkles,
  Target,
  Download,
  ClipboardCopy,
  FileArchive,
  PenTool,
  FolderOpen,
  Loader2,
  Trash2,
} from "lucide-react";
import { useAuth } from "@/components/providers";
import {
  buildCoachActions,
  deleteApplication,
  generateApplicationModules,
  patchApplication,
  regenerateModule,
  restoreDocVersion,
  setTaskStatus,
  snapshotDocVersion,
  trackEvent,
} from "@/lib/firestore";
import { useApplication, useEvidence, useTasks } from "@/lib/firestore";
import type { ModuleKey } from "@/lib/firestore";
import { toast } from "@/hooks";
import {
  downloadPdf,
  downloadDocx,
  downloadImage,
  downloadAllAsZip,
  buildBenchmarkHtml,
  buildGapAnalysisHtml,
  buildLearningPlanHtml,
} from "@/lib/export";

import { ScoreboardHeader } from "@/components/workspace/scoreboard-header";
import { CoachPanel } from "@/components/workspace/coach-panel";
import { ModuleCard } from "@/components/workspace/module-card";
import { TaskQueue } from "@/components/workspace/task-queue";
import { KeywordChips } from "@/components/workspace/keyword-chips";
import { EvidencePicker } from "@/components/workspace/evidence-picker";
import { VersionHistoryDrawer } from "@/components/workspace/version-history-drawer";
import { DocEditorModule, ExportCard, EmptyState } from "@/components/workspace/doc-editor-module";
import { AgentProgress } from "@/components/workspace/agent-progress";
import { QualityReport } from "@/components/workspace/quality-report";
import { useAgentStatus } from "@/hooks/use-agent-status";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function stripHtml(html: string) {
  return (html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function escapeHtml(text: string) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ApplicationWorkspacePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const appId = params.id;
  const searchParams = useSearchParams();

  const { user } = useAuth();
  const { data: app, loading } = useApplication(appId);
  const { data: evidence = [] } = useEvidence(user?.uid || null, 200);
  const { data: tasks = [], stats: taskStats } = useTasks(user?.uid || null, appId, 200);

  const [tab, setTab] = useState(() => searchParams.get("tab") || "overview");
  const [cvMode, setCvMode] = useState<"edit" | "diff">("edit");
  const [clMode, setClMode] = useState<"edit" | "diff">("edit");
  const [psMode, setPsMode] = useState<"edit" | "diff">("edit");
  const [portfolioMode, setPortfolioMode] = useState<"edit" | "diff">("edit");

  const cvEditorRef = useRef<any>(null);
  const clEditorRef = useRef<any>(null);
  const psEditorRef = useRef<any>(null);
  const portfolioEditorRef = useRef<any>(null);
  const [cvEditor, setCvEditor] = useState<any>(null);
  const [clEditor, setClEditor] = useState<any>(null);
  const [psEditor, setPsEditor] = useState<any>(null);
  const [portfolioEditor, setPortfolioEditor] = useState<any>(null);
  const [autoInsertedEvidence, setAutoInsertedEvidence] = useState<string | null>(null);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<"cv" | "coverLetter" | "personalStatement" | "portfolio">("cv");

  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsTarget, setVersionsTarget] = useState<"cv" | "coverLetter" | "personalStatement" | "portfolio">("cv");

  const [cvLocal, setCvLocal] = useState<string>("");
  const [clLocal, setClLocal] = useState<string>("");
  const [psLocal, setPsLocal] = useState<string>("");
  const [portfolioLocal, setPortfolioLocal] = useState<string>("");

  const [exporting, setExporting] = useState(false);
  const [regeneratingModule, setRegeneratingModule] = useState<string | null>(null);
  const [regeneratingAll, setRegeneratingAll] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { state: agentState, subscribe: agentSubscribe, handleAgentEvent, handleComplete, handleError: handleAgentError, reset: agentReset } = useAgentStatus();

  // Track workspace views
  useEffect(() => {
    if (!user || !appId) return;
    trackEvent(user.uid, { name: "view_workspace", appId });
  }, [appId, user]);

  // Keep tab in sync with URL when deep-linking.
  useEffect(() => {
    const t = searchParams.get("tab");
    if (!t) return;
    setTab((prev) => (prev === t ? prev : t));
  }, [searchParams]);

  // Sync local editor state when doc loads/changes.
  useEffect(() => {
    if (!app) return;
    setCvLocal(app.cvHtml || "");
    setClLocal(app.coverLetterHtml || "");
    setPsLocal(app.personalStatementHtml || "");
    setPortfolioLocal(app.portfolioHtml || "");
  }, [app?.cvHtml, app?.coverLetterHtml, app?.personalStatementHtml, app?.portfolioHtml]);

  // Debounced persistence for editors — use refs to avoid effect re-runs on app changes
  const appRef = useRef(app);
  appRef.current = app;

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (cvLocal !== (appRef.current?.cvHtml || "")) {
        patchApplication(appId, { cvHtml: cvLocal });
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, cvLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (clLocal !== (appRef.current?.coverLetterHtml || "")) {
        patchApplication(appId, { coverLetterHtml: clLocal });
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, clLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (psLocal !== (appRef.current?.personalStatementHtml || "")) {
        patchApplication(appId, { personalStatementHtml: psLocal });
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, psLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (portfolioLocal !== (appRef.current?.portfolioHtml || "")) {
        patchApplication(appId, { portfolioHtml: portfolioLocal });
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, portfolioLocal]);

  const keywords = useMemo(() => app?.benchmark?.keywords ?? [], [app?.benchmark?.keywords]);
  const missing = useMemo(() => app?.gaps?.missingKeywords ?? [], [app?.gaps?.missingKeywords]);

  // Pre-strip HTML once per content change — avoids re-stripping per keyword per render
  const strippedCv = useMemo(() => stripHtml(cvLocal).toLowerCase(), [cvLocal]);
  const strippedCl = useMemo(() => stripHtml(clLocal).toLowerCase(), [clLocal]);
  const strippedPs = useMemo(() => stripHtml(psLocal).toLowerCase(), [psLocal]);
  const strippedPortfolio = useMemo(() => stripHtml(portfolioLocal).toLowerCase(), [portfolioLocal]);

  const coachActions = useMemo(() => {
    if (!app || !user) return [];
    const actions = buildCoachActions({
      missingKeywords: missing,
      factsLocked: app.factsLocked ?? false,
      evidenceCount: evidence.length,
    });

    return actions.map((a) => {
      if (a.kind === "collect") {
        return { ...a, onClick: () => router.push("/evidence") };
      }
      if (a.kind === "review") {
        return { ...a, onClick: () => router.push(`/new?appId=${appId}&step=1`) };
      }
      if (a.kind === "fix") {
        return { ...a, onClick: () => setTab("cv") };
      }
      return { ...a, onClick: () => {
        setVersionsTarget("cv");
        setVersionsOpen(true);
      } };
    });
  }, [app, appId, evidence.length, missing, router, user]);

  const title = app?.title || app?.confirmedFacts?.jobTitle || "Application workspace";
  const subtitle = app?.confirmedFacts?.company ? `@ ${app.confirmedFacts.company}` : undefined;

  const isCoveredCv = useCallback((kw: string) => strippedCv.includes(kw.toLowerCase()), [strippedCv]);
  const isCoveredCl = useCallback((kw: string) => strippedCl.includes(kw.toLowerCase()), [strippedCl]);
  const isCoveredPs = useCallback((kw: string) => strippedPs.includes(kw.toLowerCase()), [strippedPs]);
  const isCoveredPortfolio = useCallback((kw: string) => strippedPortfolio.includes(kw.toLowerCase()), [strippedPortfolio]);

  const onToggleTask = async (t: any) => {
    if (!user) return;
    try {
      const next = t.status === "done" ? "todo" : "done";
      await setTaskStatus(user.uid, t.id, next);
      if (next === "done") {
        await trackEvent(user.uid, { name: "task_completed", appId: t.appId ?? undefined, properties: { taskId: t.id } });
      }
    } catch (err) {
      console.error("Task toggle failed:", err);
    }
  };

  const openPicker = (target: "cv" | "coverLetter" | "personalStatement" | "portfolio") => {
    setPickerTarget(target);
    setPickerOpen(true);
  };

  const buildEvidenceHtml = (e: any) => {
    const url = e.url || e.storageUrl || "";
    const bulletText = `${e.title}${e.description ? ` — ${e.description}` : ""}${url ? ` (${url})` : ""}`;
    return `<ul><li>${escapeHtml(bulletText)}</li></ul>`;
  };

  const onPickEvidence = (e: any) => {
    const html = buildEvidenceHtml(e);
    let editor: any = null;
    if (pickerTarget === "cv") editor = cvEditorRef.current;
    else if (pickerTarget === "coverLetter") editor = clEditorRef.current;
    else if (pickerTarget === "personalStatement") editor = psEditorRef.current;
    else if (pickerTarget === "portfolio") editor = portfolioEditorRef.current;
    editor?.chain?.().focus().insertContent(html).run();
  };

  // Auto-insert evidence from the Evidence Vault deep-link.
  useEffect(() => {
    if (!user) return;
    const insertEvidenceId = searchParams.get("insertEvidence");
    if (!insertEvidenceId) return;
    if (autoInsertedEvidence === insertEvidenceId) return;

    const insertTarget = searchParams.get("insertTarget") === "cover" ? "cover" : "cv";
    const targetTab = insertTarget === "cover" ? "cover" : "cv";

    if (tab !== targetTab) {
      setTab(targetTab);
      const qs = new URLSearchParams(searchParams.toString());
      qs.set("tab", targetTab);
      const nextUrl = qs.toString() ? `/applications/${appId}?${qs.toString()}` : `/applications/${appId}`;
      router.replace(nextUrl);
      return;
    }

    if (insertTarget === "cv" && cvMode !== "edit") {
      setCvMode("edit");
      return;
    }
    if (insertTarget === "cover" && clMode !== "edit") {
      setClMode("edit");
      return;
    }

    const editor = insertTarget === "cover" ? clEditor : cvEditor;
    if (!editor) return;

    const ev = evidence.find((x) => x.id === insertEvidenceId);
    if (!ev) return;

    editor.chain().focus().insertContent(buildEvidenceHtml(ev)).run();
    setAutoInsertedEvidence(insertEvidenceId);

    const qs = new URLSearchParams(searchParams.toString());
    qs.delete("insertEvidence");
    qs.delete("insertTarget");
    const nextUrl = qs.toString() ? `/applications/${appId}?${qs.toString()}` : `/applications/${appId}`;
    router.replace(nextUrl);
  }, [
    appId,
    autoInsertedEvidence,
    clEditor,
    clMode,
    cvEditor,
    cvMode,
    evidence,
    router,
    searchParams,
    tab,
    user,
  ]);

  const regenerate = async (module: ModuleKey) => {
    if (!user || !app || regeneratingModule || regeneratingAll) return;
    setRegeneratingModule(module);
    try {
      await regenerateModule({
        userId: user.uid,
        appId,
        module,
        evidenceCount: evidence.length,
      });
      toast.success("Regenerated!", `${module} has been regenerated with fresh AI content.`);
    } catch (err: any) {
      toast.error("Regeneration failed", err?.message ?? "Make sure the backend is running and try again.");
    } finally {
      setRegeneratingModule(null);
    }
  };

  const regenerateAll = async () => {
    if (!user || !app || regeneratingAll || regeneratingModule) return;
    if (!app.confirmedFacts) {
      toast.error("Cannot regenerate", "This application is missing the original job/resume data needed to regenerate.");
      return;
    }
    setRegeneratingAll(true);
    try {
      await generateApplicationModules(appId, user.uid, app.confirmedFacts);
      toast.success("All modules regenerated! 🎉", "Your application has been refreshed with AI-generated content.");
    } catch (err: any) {
      toast.error("Regeneration failed", err?.message ?? "Make sure the backend is running and try again.");
    } finally {
      setRegeneratingAll(false);
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!user) return;
    setDeleting(true);
    try {
      await deleteApplication(appId);
      await trackEvent(user.uid, { name: "app_deleted", appId });
      toast.success("Workspace deleted", "The application has been permanently removed.");
      router.push("/dashboard");
    } catch (err: any) {
      toast.error("Delete failed", err?.message ?? "Something went wrong.");
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  if (loading || !app) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <Skeleton className="h-[520px] w-full rounded-2xl" />
          <Skeleton className="h-[520px] w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <ScoreboardHeader title={title} subtitle={subtitle} scorecard={app.scores} />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 gap-2 rounded-xl text-muted-foreground hover:text-destructive hover:border-destructive/30 hover:bg-destructive/5 transition-colors"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="min-w-0">
          <Tabs
            value={tab}
            onValueChange={(next) => {
              setTab(next);
              const qs = new URLSearchParams(searchParams.toString());
              qs.set("tab", next);
              const nextUrl = qs.toString() ? `/applications/${appId}?${qs.toString()}` : `/applications/${appId}`;
              router.replace(nextUrl);
            }}
          >
            <TabsList className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="benchmark">Benchmark</TabsTrigger>
              <TabsTrigger value="gaps">Gap analysis</TabsTrigger>
              <TabsTrigger value="learning">Learning plan</TabsTrigger>
              <TabsTrigger value="cv">Tailored CV</TabsTrigger>
              <TabsTrigger value="cover">Cover letter</TabsTrigger>
              <TabsTrigger value="statement">Personal statement</TabsTrigger>
              <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
              <TabsTrigger value="export">Export</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-4">
              {/* Regenerate All banner */}
              <div className="mb-4 flex items-center justify-between rounded-2xl border border-primary/20 bg-primary/5 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                    <Sparkles className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">Regenerate All Modules</p>
                    <p className="text-xs text-muted-foreground">
                      Re-run the full AI pipeline to refresh every document with new content.
                    </p>
                  </div>
                </div>
                <Button
                  className="gap-2 rounded-xl"
                  onClick={regenerateAll}
                  disabled={regeneratingAll || !!regeneratingModule}
                  loading={regeneratingAll}
                >
                  {regeneratingAll ? (
                    "Regenerating…"
                  ) : (
                    <><RefreshCw className="h-4 w-4" /> Regenerate All</>
                  )}
                </Button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <ModuleCard
                  title="Benchmark"
                  description="Ideal candidate signal + rubric"
                  status={app.modules.benchmark}
                  icon={<Target className="h-5 w-5" />}
                  onOpen={() => setTab("benchmark")}
                  onRegenerate={() => regenerate("benchmark")}
                />
                <ModuleCard
                  title="Gap analysis"
                  description="Missing keywords + recommendations + tasks"
                  status={app.modules.gaps}
                  icon={<Layers className="h-5 w-5" />}
                  onOpen={() => setTab("gaps")}
                  onRegenerate={() => regenerate("gaps")}
                />
                <ModuleCard
                  title="Learning plan"
                  description="Skill sprints + outcomes practice"
                  status={app.modules.learningPlan}
                  icon={<GraduationCap className="h-5 w-5" />}
                  onOpen={() => setTab("learning")}
                  onRegenerate={() => regenerate("learningPlan")}
                />
                <ModuleCard
                  title="Tailored CV"
                  description="Edit, diff, version, iterate"
                  status={app.modules.cv}
                  icon={<FileText className="h-5 w-5" />}
                  onOpen={() => setTab("cv")}
                  onRegenerate={() => regenerate("cv")}
                />
                <ModuleCard
                  title="Cover Letter"
                  description="Evidence-first narrative"
                  status={app.modules.coverLetter}
                  icon={<FileText className="h-5 w-5" />}
                  onOpen={() => setTab("cover")}
                  onRegenerate={() => regenerate("coverLetter")}
                />
                <ModuleCard
                  title="Personal Statement"
                  description="Compelling motivation narrative"
                  status={app.modules.personalStatement}
                  icon={<PenTool className="h-5 w-5" />}
                  onOpen={() => setTab("statement")}
                  onRegenerate={() => regenerate("personalStatement")}
                />
                <ModuleCard
                  title="Portfolio & Evidence"
                  description="Proof of knowledge + projects"
                  status={app.modules.portfolio}
                  icon={<FolderOpen className="h-5 w-5" />}
                  onOpen={() => setTab("portfolio")}
                  onRegenerate={() => regenerate("portfolio")}
                />
              </div>

              <div className="mt-6">
                <TaskQueue tasks={tasks} onToggle={onToggleTask} />
              </div>
            </TabsContent>

            <TabsContent value="benchmark" className="mt-4">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">Benchmark — Ideal Candidate</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      AI-generated profile of the perfect candidate. Your north star.
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => regenerate("benchmark")} disabled={regeneratingModule === "benchmark"}>
                    {regeneratingModule === "benchmark" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {regeneratingModule === "benchmark" ? "Working…" : "Regenerate"}
                  </Button>
                </div>

                <Separator className="my-4" />

                {app.benchmark ? (
                  <div className="space-y-5">
                    <div className="rounded-xl bg-gradient-to-br from-primary/5 via-violet-500/5 to-blue-500/5 border border-primary/10 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-primary">
                        <Sparkles className="h-3.5 w-3.5" />
                        AI Analysis
                      </div>
                      <div className="mt-2 text-sm text-foreground/80 leading-relaxed">
                        {toLabel(app.benchmark.summary)}
                      </div>
                    </div>

                    {(app.benchmark as any).idealProfile && (
                      <div className="rounded-xl border p-4">
                        <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Ideal Candidate</div>
                        <div className="mt-2 text-base font-bold">{toLabel((app.benchmark as any).idealProfile?.title || (app.benchmark as any).idealProfile?.name)}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {(app.benchmark as any).idealProfile?.years_experience} yrs experience
                        </div>
                      </div>
                    )}

                    {(app.benchmark as any).idealSkills?.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold mb-3">Key Skills Required</div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {((app.benchmark as any).idealSkills ?? []).slice(0, 8).map((s: any, i: number) => (
                            <div key={toLabel(s?.name) || i} className="flex items-center justify-between rounded-lg border p-2.5">
                              <div className="flex items-center gap-2">
                                <div className={`h-2 w-2 rounded-full ${s?.importance === "critical" ? "bg-rose-500" : s?.importance === "important" ? "bg-amber-500" : "bg-blue-500"}`} />
                                <span className="text-sm font-medium">{toLabel(s?.name)}</span>
                              </div>
                              <Badge variant="secondary" className="text-[10px]">{toLabel(s?.level || s?.importance)}</Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="text-xs font-semibold">Scoring Rubric</div>
                      <ul className="mt-2 space-y-1.5">
                        {(app.benchmark.rubric ?? []).map((r: any, idx: number) => {
                          const label = typeof r === "string" ? r : r?.dimension ?? `Dimension ${idx + 1}`;
                          return (
                            <li key={label} className="flex items-start gap-2 text-sm text-muted-foreground">
                              <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/40" />
                              {label}
                            </li>
                          );
                        })}
                      </ul>
                    </div>

                    <div>
                      <div className="text-xs font-semibold">Target Keywords ({(app.benchmark.keywords ?? []).length})</div>
                      <div className="mt-2">
                        <KeywordChips keywords={app.benchmark.keywords ?? []} isCovered={() => true} />
                      </div>
                    </div>

                    {/* ── Benchmark Ideal CV ─────────────────────────── */}
                    {(app.benchmark as any).benchmarkCvHtml && (
                      <div className="mt-2">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <div className="text-xs font-semibold">Ideal Candidate CV</div>
                            <div className="mt-0.5 text-[10px] text-muted-foreground">
                              A full reference CV — your name with benchmark-level experience. Read-only north star.
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              className="gap-1.5 rounded-xl text-xs"
                              onClick={async () => {
                                try {
                                  await downloadPdf((app.benchmark as any).benchmarkCvHtml, {
                                    filename: "HireStack_Benchmark_CV",
                                    documentType: "cv",
                                  });
                                } catch (err) {
                                  console.error("Benchmark CV export failed:", err);
                                }
                              }}
                            >
                              <Download className="h-3.5 w-3.5" />
                              PDF
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="gap-1.5 rounded-xl text-xs"
                              onClick={() => {
                                navigator.clipboard.writeText(
                                  stripHtml((app.benchmark as any).benchmarkCvHtml || "")
                                );
                                toast.success("Copied!", "Benchmark CV text copied to clipboard.");
                              }}
                            >
                              <ClipboardCopy className="h-3.5 w-3.5" />
                              Copy
                            </Button>
                          </div>
                        </div>
                        <div className="rounded-xl border bg-white/50 dark:bg-background/50 overflow-hidden">
                          <div
                            className="prose prose-sm max-w-none p-5 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:border-b [&_h2]:pb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-3 [&_ul]:mt-1 [&_li]:text-xs [&_p]:text-xs [&_p]:text-muted-foreground"
                            dangerouslySetInnerHTML={{ __html: (app.benchmark as any).benchmarkCvHtml }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <EmptyState
                    title="Benchmark not generated yet."
                    body="Run the wizard generation or regenerate the module here."
                    action={<Button onClick={() => regenerate("benchmark")} loading={regeneratingModule === "benchmark"}>Generate benchmark</Button>}
                  />
                )}
              </div>
            </TabsContent>

            <TabsContent value="gaps" className="mt-4">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">Gap analysis</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Gaps create the action queue. Fix one gap at a time, with evidence.
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => regenerate("gaps")} disabled={regeneratingModule === "gaps"}>
                    {regeneratingModule === "gaps" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {regeneratingModule === "gaps" ? "Working…" : "Regenerate"}
                  </Button>
                </div>

                <Separator className="my-4" />

                {app.gaps ? (
                  <div className="space-y-4">
                    {(app.gaps as any).compatibility != null && (
                      <div className="rounded-xl bg-gradient-to-br from-primary/5 to-violet-500/5 border border-primary/10 p-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-xs font-semibold text-primary">Compatibility Score</div>
                            <div className="mt-1 text-2xl font-bold">{(app.gaps as any).compatibility}%</div>
                          </div>
                          <div className="text-right text-xs text-muted-foreground">
                            {(app.gaps as any).compatibility >= 70 ? "Strong match" : (app.gaps as any).compatibility >= 45 ? "Competitive" : "Needs work"}
                          </div>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full transition-all ${(app.gaps as any).compatibility >= 70 ? "bg-emerald-500" : (app.gaps as any).compatibility >= 45 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${(app.gaps as any).compatibility}%` }} />
                        </div>
                        {toLabel((app.gaps as any).summary) && (
                          <div className="mt-3 text-sm text-foreground/80 leading-relaxed">{toLabel((app.gaps as any).summary)}</div>
                        )}
                      </div>
                    )}
                    <div>
                      <div className="text-xs font-semibold">Missing keywords</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(app.gaps.missingKeywords ?? []).slice(0, 16).map((k: any, i: number) => {
                          const label = toLabel(k);
                          return (
                          <Badge key={label || i} variant="secondary" className="border bg-amber-500/10 text-amber-700 border-amber-200 text-[11px]">
                            {label}
                          </Badge>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs font-semibold">Strengths</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(app.gaps.strengths ?? []).slice(0, 12).map((k: any, i: number) => {
                          const label = toLabel(k);
                          return (
                          <Badge key={label || i} variant="secondary" className="border text-[11px]">
                            {label}
                          </Badge>
                          );
                        })}
                      </div>
                    </div>

                    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                      <div className="text-xs font-semibold text-primary">Recommendations</div>
                      <ul className="mt-2 space-y-1 text-sm text-foreground/80">
                        {(app.gaps.recommendations ?? []).map((r: any, i: number) => {
                          const label = toLabel(r);
                          return <li key={label || i}>• {label}</li>;
                        })}
                      </ul>
                    </div>

                    <TaskQueue tasks={tasks} onToggle={onToggleTask} />
                  </div>
                ) : (
                  <EmptyState
                    title="Gap analysis not generated yet."
                    body="Generate gaps to create your action queue."
                    action={<Button onClick={() => regenerate("gaps")} loading={regeneratingModule === "gaps"}>Generate gaps</Button>}
                  />
                )}
              </div>
            </TabsContent>

            <TabsContent value="learning" className="mt-4">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">Learning plan</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      A sprint-based plan built from your gaps. Each week produces proof.
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => regenerate("learningPlan")} disabled={regeneratingModule === "learningPlan"}>
                    {regeneratingModule === "learningPlan" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {regeneratingModule === "learningPlan" ? "Working…" : "Regenerate"}
                  </Button>
                </div>

                <Separator className="my-4" />

                {app.learningPlan ? (
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs font-semibold">Focus</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {(app.learningPlan.focus ?? []).map((k: any, i: number) => {
                          const label = toLabel(k);
                          return (
                          <Badge key={label || i} variant="secondary" className="border bg-purple-50 text-purple-900 border-purple-200 text-[11px]">
                            {label}
                          </Badge>
                          );
                        })}
                      </div>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      {(app.learningPlan.plan ?? []).map((w: any) => (
                        <div key={w.week} className="rounded-2xl border bg-card p-4">
                          <div className="text-sm font-semibold">{w.theme ?? `Week ${w.week}`}</div>
                          <div className="mt-2 text-xs text-muted-foreground font-medium">Outcomes</div>
                          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                            {(w.outcomes ?? w.goals ?? []).map((o: any, i: number) => {
                              const label = toLabel(o);
                              return <li key={label || i}>• {label}</li>;
                            })}
                          </ul>
                          <div className="mt-3 text-xs text-muted-foreground font-medium">Tasks</div>
                          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                            {(w.tasks ?? []).map((t: any, i: number) => {
                              const label = toLabel(t);
                              return <li key={label || i}>• {label}</li>;
                            })}
                          </ul>
                        </div>
                      ))}
                    </div>

                    <div className="rounded-2xl border bg-card p-4">
                      <div className="flex items-center gap-2">
                        <BookOpen className="h-4 w-4 text-muted-foreground" />
                        <div className="text-sm font-semibold">Resources</div>
                      </div>
                      <div className="mt-3 space-y-2">
                        {(app.learningPlan.resources ?? []).map((r: any, rIdx: number) => (
                          <div key={toLabel(r.title) || rIdx} className="rounded-xl border p-3">
                            <div className="text-sm font-medium">{toLabel(r.title)}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {toLabel(r.provider) || "Resource"} · {toLabel(r.timebox) || "Self-paced"} {r.skill ? `· ${toLabel(r.skill)}` : ""}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    title="Learning plan not generated yet."
                    body="Generate it to get sprint tasks + resources."
                    action={<Button onClick={() => regenerate("learningPlan")} loading={regeneratingModule === "learningPlan"}>Generate learning plan</Button>}
                  />
                )}
              </div>
            </TabsContent>

            <TabsContent value="cv" className="mt-4">
              <DocEditorModule
                title="Tailored CV"
                subtitle="Two-pane editing: write + validate against keywords."
                mode={cvMode}
                onModeChange={setCvMode}
                keywords={keywords}
                missingKeywords={missing}
                isCovered={isCoveredCv}
                value={cvLocal}
                onChange={setCvLocal}
                editorRef={cvEditorRef}
                onEditorReady={setCvEditor}
                onPickEvidence={() => openPicker("cv")}
                onRegenerate={() => regenerate("cv")}
                isRegenerating={regeneratingModule === "cv"}
                onOpenVersions={() => {
                  setVersionsTarget("cv");
                  setVersionsOpen(true);
                }}
                baseHtml={app.confirmedFacts?.resume?.text || ""}
              />
            </TabsContent>

            <TabsContent value="cover" className="mt-4">
              <DocEditorModule
                title="Cover letter"
                subtitle="Evidence-first narrative, not fluff."
                mode={clMode}
                onModeChange={setClMode}
                keywords={keywords}
                missingKeywords={missing}
                isCovered={isCoveredCl}
                value={clLocal}
                onChange={setClLocal}
                editorRef={clEditorRef}
                onEditorReady={setClEditor}
                onPickEvidence={() => openPicker("coverLetter")}
                onRegenerate={() => regenerate("coverLetter")}
                isRegenerating={regeneratingModule === "coverLetter"}
                onOpenVersions={() => {
                  setVersionsTarget("coverLetter");
                  setVersionsOpen(true);
                }}
                baseHtml={app.confirmedFacts?.resume?.text || ""}
              />
            </TabsContent>

            <TabsContent value="statement" className="mt-4">
              <DocEditorModule
                title="Personal statement"
                subtitle="Your compelling motivation narrative — authentic, specific, memorable."
                mode={psMode}
                onModeChange={setPsMode}
                keywords={keywords}
                missingKeywords={missing}
                isCovered={isCoveredPs}
                value={psLocal}
                onChange={setPsLocal}
                editorRef={psEditorRef}
                onEditorReady={setPsEditor}
                onPickEvidence={() => openPicker("personalStatement")}
                onRegenerate={() => regenerate("personalStatement")}
                isRegenerating={regeneratingModule === "personalStatement"}
                onOpenVersions={() => {
                  setVersionsTarget("personalStatement");
                  setVersionsOpen(true);
                }}
                baseHtml={app.confirmedFacts?.resume?.text || ""}
              />
            </TabsContent>

            <TabsContent value="portfolio" className="mt-4">
              <DocEditorModule
                title="Portfolio & evidence"
                subtitle="Showcase projects and proof of knowledge — irrefutable evidence of capability."
                mode={portfolioMode}
                onModeChange={setPortfolioMode}
                keywords={keywords}
                missingKeywords={missing}
                isCovered={isCoveredPortfolio}
                value={portfolioLocal}
                onChange={setPortfolioLocal}
                editorRef={portfolioEditorRef}
                onEditorReady={setPortfolioEditor}
                onPickEvidence={() => openPicker("portfolio")}
                onRegenerate={() => regenerate("portfolio")}
                isRegenerating={regeneratingModule === "portfolio"}
                onOpenVersions={() => {
                  setVersionsTarget("portfolio");
                  setVersionsOpen(true);
                }}
                baseHtml=""
              />
            </TabsContent>

            <TabsContent value="export" className="mt-4">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">Export & Download</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Download professionally designed PDFs of every document. One click, ready to submit.
                    </div>
                  </div>
                  <Button
                    variant="default"
                    size="sm"
                    className="gap-2 rounded-xl"
                    disabled={exporting}
                    onClick={async () => {
                      if (!user) return;
                      setExporting(true);
                      try {
                        await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "zip_all" } });
                        await downloadAllAsZip({
                          jobTitle: app.confirmedFacts?.jobTitle || "Role",
                          company: app.confirmedFacts?.company || "Company",
                          cvHtml: cvLocal || undefined,
                          coverLetterHtml: clLocal || undefined,
                          personalStatementHtml: psLocal || undefined,
                          portfolioHtml: portfolioLocal || undefined,
                          learningPlanHtml: app.learningPlan ? buildLearningPlanHtml(app.learningPlan) : undefined,
                          benchmarkHtml: app.benchmark ? buildBenchmarkHtml(app.benchmark, app.confirmedFacts?.jobTitle || "") : undefined,
                          gapAnalysisHtml: app.gaps ? buildGapAnalysisHtml(app.gaps) : undefined,
                        });
                      } catch (err) {
                        console.error("ZIP export failed:", err);
                      } finally {
                        setExporting(false);
                      }
                    }}
                  >
                    {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />}
                    Download All (ZIP)
                  </Button>
                </div>

                <Separator className="my-4" />

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <ExportCard
                    title="Tailored CV"
                    description="ATS-optimized, keyword-rich, strategically enhanced."
                    hasContent={!!cvLocal}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cv_pdf" } });
                      await downloadPdf(cvLocal, { filename: "HireStack_CV", documentType: "cv" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cv_docx" } });
                      await downloadDocx(cvLocal, { filename: "HireStack_CV", documentType: "cv" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cv_jpg" } });
                      await downloadImage(cvLocal, { filename: "HireStack_CV", documentType: "cv", format: "jpg" });
                    }}
                    onCopyText={() => navigator.clipboard.writeText(stripHtml(cvLocal))}
                  />
                  <ExportCard
                    title="Cover Letter"
                    description="Compelling, evidence-backed narrative."
                    hasContent={!!clLocal}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cl_pdf" } });
                      await downloadPdf(clLocal, { filename: "HireStack_Cover_Letter", documentType: "coverLetter" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cl_docx" } });
                      await downloadDocx(clLocal, { filename: "HireStack_Cover_Letter", documentType: "coverLetter" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "cl_jpg" } });
                      await downloadImage(clLocal, { filename: "HireStack_Cover_Letter", documentType: "coverLetter", format: "jpg" });
                    }}
                    onCopyText={() => navigator.clipboard.writeText(stripHtml(clLocal))}
                  />
                  <ExportCard
                    title="Personal Statement"
                    description="Authentic motivation narrative."
                    hasContent={!!psLocal}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "ps_pdf" } });
                      await downloadPdf(psLocal, { filename: "HireStack_Personal_Statement", documentType: "personalStatement" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "ps_docx" } });
                      await downloadDocx(psLocal, { filename: "HireStack_Personal_Statement", documentType: "personalStatement" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "ps_jpg" } });
                      await downloadImage(psLocal, { filename: "HireStack_Personal_Statement", documentType: "personalStatement", format: "jpg" });
                    }}
                    onCopyText={() => navigator.clipboard.writeText(stripHtml(psLocal))}
                  />
                  <ExportCard
                    title="Portfolio & Evidence"
                    description="Project showcase with impact metrics."
                    hasContent={!!portfolioLocal}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "portfolio_pdf" } });
                      await downloadPdf(portfolioLocal, { filename: "HireStack_Portfolio", documentType: "portfolio" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "portfolio_docx" } });
                      await downloadDocx(portfolioLocal, { filename: "HireStack_Portfolio", documentType: "portfolio" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "portfolio_jpg" } });
                      await downloadImage(portfolioLocal, { filename: "HireStack_Portfolio", documentType: "portfolio", format: "jpg" });
                    }}
                    onCopyText={() => navigator.clipboard.writeText(stripHtml(portfolioLocal))}
                  />
                  <ExportCard
                    title="Learning Plan"
                    description="Sprint-based skill development roadmap."
                    hasContent={!!app.learningPlan}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "learning_pdf" } });
                      const html = buildLearningPlanHtml(app.learningPlan);
                      await downloadPdf(html, { filename: "HireStack_Learning_Plan", documentType: "learningPlan" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "learning_docx" } });
                      const html = buildLearningPlanHtml(app.learningPlan);
                      await downloadDocx(html, { filename: "HireStack_Learning_Plan", documentType: "learningPlan" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "learning_jpg" } });
                      const html = buildLearningPlanHtml(app.learningPlan);
                      await downloadImage(html, { filename: "HireStack_Learning_Plan", documentType: "learningPlan", format: "jpg" });
                    }}
                    onCopyText={() => {
                      const html = buildLearningPlanHtml(app.learningPlan);
                      navigator.clipboard.writeText(stripHtml(html));
                    }}
                  />
                  <ExportCard
                    title="Gap Analysis"
                    description="Skills gap assessment with recommendations."
                    hasContent={!!app.gaps}
                    onDownloadPdf={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "gaps_pdf" } });
                      const html = buildGapAnalysisHtml(app.gaps);
                      await downloadPdf(html, { filename: "HireStack_Gap_Analysis", documentType: "gapAnalysis" });
                    }}
                    onDownloadDocx={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "gaps_docx" } });
                      const html = buildGapAnalysisHtml(app.gaps);
                      await downloadDocx(html, { filename: "HireStack_Gap_Analysis", documentType: "gapAnalysis" });
                    }}
                    onDownloadImage={async () => {
                      if (!user) return;
                      await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "gaps_jpg" } });
                      const html = buildGapAnalysisHtml(app.gaps);
                      await downloadImage(html, { filename: "HireStack_Gap_Analysis", documentType: "gapAnalysis", format: "jpg" });
                    }}
                    onCopyText={() => {
                      const html = buildGapAnalysisHtml(app.gaps);
                      navigator.clipboard.writeText(stripHtml(html));
                    }}
                  />
                </div>

                <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
                  <div className="text-xs font-semibold text-primary">Pro tip</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Use "Download All (ZIP)" to get every document as a branded PDF + Word bundle — ready to attach to any application. Snapshot your versions before exporting to keep a history.
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4">
          {(agentState.isRunning || agentState.stages.length > 0) && (
            <div className="rounded-xl border p-4 bg-card">
              <AgentProgress
                stages={agentState.stages}
                isRunning={agentState.isRunning}
              />
            </div>
          )}
          {Object.keys(agentState.qualityScores).length > 0 && (
            <div className="rounded-xl border p-4 bg-card">
              <QualityReport
                scores={agentState.qualityScores}
                factCheck={agentState.factCheckSummary}
              />
            </div>
          )}
          <CoachPanel actions={coachActions} statusLine={`${taskStats.remaining} open tasks · ${evidence.length} evidence`} />
        </div>
      </div>

      <EvidencePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        evidence={evidence}
        onPick={onPickEvidence}
      />

      <VersionHistoryDrawer
        open={versionsOpen}
        onOpenChange={setVersionsOpen}
        versions={
          versionsTarget === "cv"
            ? (app.cvVersions ?? [])
            : versionsTarget === "coverLetter"
              ? (app.clVersions ?? [])
              : versionsTarget === "personalStatement"
                ? (app.psVersions ?? [])
                : (app.portfolioVersions ?? [])
        }
        onSnapshot={async (label) => {
          await snapshotDocVersion(appId, versionsTarget, label);
        }}
        onRestore={async (versionId) => {
          await restoreDocVersion(appId, versionsTarget, versionId);
        }}
      />

      {/* Delete workspace confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle>Delete workspace</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <span className="font-medium text-foreground">&ldquo;{title}&rdquo;</span>?
              This will permanently remove all generated documents, benchmarks, gap analyses, and version history. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" className="rounded-xl" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" className="rounded-xl gap-2" onClick={handleDeleteWorkspace} loading={deleting}>
              <Trash2 className="h-4 w-4" />
              {deleting ? "Deleting…" : "Delete workspace"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
