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
  LayoutGrid,
  BarChart3,
  Package,
  Search,
  Building2,
  Globe,
  Newspaper,
  Users,
  Lightbulb,
  Shield,
  TrendingUp,
  FileSearch,
  CheckCircle2,
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
  generateOptionalDocument,
} from "@/lib/firestore";
import { useApplication, useEvidence, useTasks } from "@/lib/firestore";
import type { ModuleKey } from "@/lib/firestore";
import type { PipelineProgress } from "@/lib/firestore/ops";
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
import type { DocMode } from "@/components/workspace/diff-toggle";
import { sanitizeHtml } from "@/lib/sanitize";
import { AgentProgress } from "@/components/workspace/agent-progress";
import { AgentTimelineRail } from "@/components/workspace/agent-timeline-rail";
import { EvidenceInspector } from "@/components/workspace/evidence-inspector";
import { RiskPanel } from "@/components/workspace/risk-panel";
import { ValidationDrawer } from "@/components/workspace/validation-drawer";
import { ReplayDrawer } from "@/components/workspace/replay-drawer";
import { QualityReport } from "@/components/workspace/quality-report";
import { useAgentStatus } from "@/hooks/use-agent-status";
import { useDownloadGate } from "@/hooks/use-download-gate";
import { ATSScorePanel } from "@/components/workspace/ats-score-panel";
import { SignupModal } from "@/components/auth/signup-modal";
import { AITrace } from "@/components/ui/ai-trace";

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
  const { gatedDownload, showSignup, setShowSignup, onSignupSuccess } = useDownloadGate();

  const { user, session } = useAuth();
  const userId = user?.uid || user?.id || null;
  const { data: app, loading } = useApplication(appId);
  const { data: evidence = [] } = useEvidence(userId, 200);
  const { data: tasks = [], stats: taskStats } = useTasks(userId, appId, 200);

  const [tab, setTab] = useState(() => searchParams.get("tab") || "overview");
  const [cvMode, setCvMode] = useState<DocMode>("view");
  const [clMode, setClMode] = useState<DocMode>("view");
  const [psMode, setPsMode] = useState<DocMode>("view");
  const [portfolioMode, setPortfolioMode] = useState<DocMode>("view");

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
  const [liveProgress, setLiveProgress] = useState<number>(0);
  const [generatingDocKey, setGeneratingDocKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { state: agentState, subscribe: agentSubscribe, handleAgentEvent, handleComplete, handleError: handleAgentError, reset: agentReset, setReplayReport } = useAgentStatus();

  // Auto-clear save indicator
  useEffect(() => {
    if (saveStatus === "saved" || saveStatus === "error") {
      const t = setTimeout(() => setSaveStatus("idle"), 2000);
      return () => clearTimeout(t);
    }
  }, [saveStatus]);

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
  }, [app, app?.cvHtml, app?.coverLetterHtml, app?.personalStatementHtml, app?.portfolioHtml]);

  // Debounced persistence for editors — use refs to avoid effect re-runs on app changes
  const appRef = useRef(app);
  appRef.current = app;

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (cvLocal !== (appRef.current?.cvHtml || "")) {
        setSaveStatus("saving");
        patchApplication(appId, { cvHtml: cvLocal }).then(() => setSaveStatus("saved")).catch(() => setSaveStatus("error"));
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, cvLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (clLocal !== (appRef.current?.coverLetterHtml || "")) {
        setSaveStatus("saving");
        patchApplication(appId, { coverLetterHtml: clLocal }).then(() => setSaveStatus("saved")).catch(() => setSaveStatus("error"));
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, clLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (psLocal !== (appRef.current?.personalStatementHtml || "")) {
        setSaveStatus("saving");
        patchApplication(appId, { personalStatementHtml: psLocal }).then(() => setSaveStatus("saved")).catch(() => setSaveStatus("error"));
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, psLocal]);

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (portfolioLocal !== (appRef.current?.portfolioHtml || "")) {
        setSaveStatus("saving");
        patchApplication(appId, { portfolioHtml: portfolioLocal }).then(() => setSaveStatus("saved")).catch(() => setSaveStatus("error"));
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
    const es = agentState.evidenceSummary;
    const vr = agentState.validationReport;
    const fa = agentState.finalAnalysis;

    const actions = buildCoachActions({
      missingKeywords: missing,
      factsLocked: app.factsLocked ?? false,
      evidenceCount: evidence.length,
      fabricatedClaims: es?.fabricated_count,
      unsupportedClaims: es?.unlinked_count,
      validationHardFailures: vr?.hard_failures,
      validationSoftWarnings: vr?.soft_warnings,
      residualMissingKeywords: (fa as any)?.missing_keywords,
      replayFailureClass: agentState.replayReport?.failure_class,
      contradictionCount: (fa as any)?.contradiction_count,
      finalATSScore: (fa as any)?.ats_score,
    });

    return actions.map((a) => {
      if (a.kind === "collect") {
        return { ...a, onClick: () => router.push("/evidence") };
      }
      if (a.kind === "review") {
        return { ...a, onClick: () => router.push(`/new?appId=${appId}&step=1`) };
      }
      if (a.kind === "fix" || a.kind === "danger") {
        return { ...a, onClick: () => setTab("cv") };
      }
      if (a.kind === "replay") {
        return { ...a, onClick: () => { /* scroll to replay drawer */ } };
      }
      return { ...a, onClick: () => {
        setVersionsTarget("cv");
        setVersionsOpen(true);
      } };
    });
  }, [app, appId, evidence.length, missing, router, user, agentState.evidenceSummary, agentState.validationReport, agentState.finalAnalysis, agentState.replayReport]);

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
      toast({ title: "Couldn't update task", description: "Please try again.", variant: "error" });
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

  // Auto-insert evidence from the evidence deep-link.
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
    setLiveProgress(0);
    try {
      await generateApplicationModules(
        appId,
        user.uid,
        app.confirmedFacts,
        undefined,
        (p: PipelineProgress) => setLiveProgress(p.progress ?? 0),
      );
      toast.success("All modules regenerated! 🎉", "Your application has been refreshed with AI-generated content.");
    } catch (err: any) {
      toast.error("Regeneration failed", err?.message ?? "Make sure the backend is running and try again.");
    } finally {
      setRegeneratingAll(false);
      setLiveProgress(0);
    }
  };

  /** Merge live SSE progress into module status during regeneration. */
  const modStatus = useCallback(
    (key: ModuleKey) => {
      const base = app?.modules?.[key];
      if (!base) return { state: "idle" as const };
      if (regeneratingAll && (base.state === "generating" || base.state === "queued") && liveProgress > 0) {
        return { ...base, progress: liveProgress };
      }
      return base;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [app?.modules, regeneratingAll, liveProgress],
  );

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
        <div className="flex items-center gap-3 shrink-0">
          {saveStatus === "saving" && <span className="text-xs text-muted-foreground animate-pulse">Saving…</span>}
          {saveStatus === "saved" && <span className="text-xs text-emerald-500">Saved</span>}
          {saveStatus === "error" && <span className="text-xs text-destructive">Save failed</span>}
          <Button
            variant="outline"
            size="sm"
            className="gap-2 rounded-xl text-muted-foreground hover:text-destructive hover:border-destructive/30 hover:bg-destructive/5 transition-colors"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
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
            <TabsList className="w-full justify-start overflow-x-auto h-auto flex-wrap gap-1 bg-muted/50 p-1.5 rounded-xl">
              <TabsTrigger value="overview" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><LayoutGrid className="h-3.5 w-3.5" />Overview</TabsTrigger>
              <TabsTrigger value="intel" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><Search className="h-3.5 w-3.5" />Intel</TabsTrigger>
              <TabsTrigger value="benchmark" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><Target className="h-3.5 w-3.5" />Benchmark</TabsTrigger>
              <TabsTrigger value="gaps" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><BarChart3 className="h-3.5 w-3.5" />Gaps</TabsTrigger>
              <TabsTrigger value="learning" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><GraduationCap className="h-3.5 w-3.5" />Learning</TabsTrigger>
              <TabsTrigger value="cv" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><FileText className="h-3.5 w-3.5" />CV</TabsTrigger>
              <TabsTrigger value="cover" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><FileText className="h-3.5 w-3.5" />Cover Letter</TabsTrigger>
              <TabsTrigger value="statement" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><PenTool className="h-3.5 w-3.5" />Statement</TabsTrigger>
              <TabsTrigger value="portfolio" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><FolderOpen className="h-3.5 w-3.5" />Portfolio</TabsTrigger>
              {/* Dynamic extra document tabs from Document Discovery */}
              {app.generatedDocuments && Object.keys(app.generatedDocuments).length > 0 && (
                Object.entries(app.generatedDocuments).map(([key, html]) => {
                  if (!html) return null;
                  // Find the label from discoveredDocuments
                  const docInfo = (app.discoveredDocuments || []).find((d: any) => d.key === key);
                  const label = docInfo?.label || key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                  return (
                    <TabsTrigger key={key} value={`extra-${key}`} className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm">
                      <Sparkles className="h-3 w-3 text-teal-500" />
                      <span className="text-xs">{label}</span>
                    </TabsTrigger>
                  );
                })
              )}
              {/* Optional documents tab — shown when ungenerated discovered docs exist */}
              {(() => {
                const generated = app.generatedDocuments || {};
                const coreKeys = new Set(["cv", "cover_letter", "personal_statement", "portfolio"]);
                const hasUngenerated = (app.discoveredDocuments || []).some(
                  (d: any) => d.key && !generated[d.key] && !coreKeys.has(d.key)
                );
                if (!hasUngenerated) return null;
                return (
                  <TabsTrigger value="optional-docs" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm">
                    <Sparkles className="h-3 w-3 text-amber-500" />
                    <span className="text-xs">Optional Docs</span>
                  </TabsTrigger>
                );
              })()}
              <TabsTrigger value="ats" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><FileSearch className="h-3.5 w-3.5" />ATS Score</TabsTrigger>
              <TabsTrigger value="export" className="gap-1.5 rounded-lg data-[state=active]:shadow-soft-sm"><Package className="h-3.5 w-3.5" />Export</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-4">
              {/* AI intelligence trace */}
              <AITrace
                variant="inline"
                className="mb-4"
                items={[
                  { label: `${keywords.length} keywords extracted`, done: true },
                  { label: `${missing.length} gaps identified`, done: true },
                  { label: `${tasks.length} tasks generated`, done: true },
                  { label: `${evidence.length} evidence items available`, done: true },
                ]}
              />
              {/* Module completion progress */}
              {(() => {
                const moduleKeys = ["benchmark", "gaps", "learningPlan", "cv", "coverLetter", "personalStatement", "portfolio"] as const;
                const completed = moduleKeys.filter((k) => app.modules[k]?.state === "ready").length;
                const pct = Math.round((completed / moduleKeys.length) * 100);
                return (
                  <div className="mb-4 rounded-2xl border bg-gradient-to-r from-primary/5 via-violet-500/5 to-transparent p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                          <Sparkles className="h-5 w-5 text-primary" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold">{completed}/{moduleKeys.length} modules complete</p>
                          <div className="mt-1.5 flex items-center gap-3">
                            <div className="h-1.5 flex-1 max-w-[200px] rounded-full bg-muted overflow-hidden">
                              <div className={`h-full rounded-full transition-all duration-500 ${pct === 100 ? "bg-emerald-500" : "bg-primary"}`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className="text-xs font-medium tabular-nums text-muted-foreground">{pct}%</span>
                          </div>
                        </div>
                      </div>
                      <Button
                        className="gap-2 rounded-xl shrink-0"
                        onClick={regenerateAll}
                        disabled={regeneratingAll || !!regeneratingModule}
                        loading={regeneratingAll}
                      >
                        {regeneratingAll ? "Regenerating…" : <><RefreshCw className="h-4 w-4" /> Regenerate All</>}
                      </Button>
                    </div>
                  </div>
                );
              })()}

              <div className="grid gap-4 md:grid-cols-2">
                <ModuleCard
                  title="Benchmark"
                  description="Ideal candidate signal + rubric"
                  status={modStatus("benchmark")}
                  icon={<Target className="h-5 w-5" />}
                  onOpen={() => setTab("benchmark")}
                  onRegenerate={() => regenerate("benchmark")}
                />
                <ModuleCard
                  title="Gap analysis"
                  description="Missing keywords + recommendations + tasks"
                  status={modStatus("gaps")}
                  icon={<Layers className="h-5 w-5" />}
                  onOpen={() => setTab("gaps")}
                  onRegenerate={() => regenerate("gaps")}
                />
                <ModuleCard
                  title="Learning plan"
                  description="Skill sprints + outcomes practice"
                  status={modStatus("learningPlan")}
                  icon={<GraduationCap className="h-5 w-5" />}
                  onOpen={() => setTab("learning")}
                  onRegenerate={() => regenerate("learningPlan")}
                />
                <ModuleCard
                  title="Tailored CV"
                  description="Edit, diff, version, iterate"
                  status={modStatus("cv")}
                  icon={<FileText className="h-5 w-5" />}
                  onOpen={() => setTab("cv")}
                  onRegenerate={() => regenerate("cv")}
                />
                <ModuleCard
                  title="Cover Letter"
                  description="Evidence-first narrative"
                  status={modStatus("coverLetter")}
                  icon={<FileText className="h-5 w-5" />}
                  onOpen={() => setTab("cover")}
                  onRegenerate={() => regenerate("coverLetter")}
                />
                <ModuleCard
                  title="Personal Statement"
                  description="Compelling motivation narrative"
                  status={modStatus("personalStatement")}
                  icon={<PenTool className="h-5 w-5" />}
                  onOpen={() => setTab("statement")}
                  onRegenerate={() => regenerate("personalStatement")}
                />
                <ModuleCard
                  title="Portfolio & Evidence"
                  description="Proof of knowledge + projects"
                  status={modStatus("portfolio")}
                  icon={<FolderOpen className="h-5 w-5" />}
                  onOpen={() => setTab("portfolio")}
                  onRegenerate={() => regenerate("portfolio")}
                />
              </div>

              <div className="mt-6">
                <TaskQueue tasks={tasks} onToggle={onToggleTask} />
              </div>
            </TabsContent>

            {/* ── Intel Tab ── */}
            <TabsContent value="intel" className="mt-4">
              {(() => {
                const intel = (app as any)?.company_intel;
                if (!intel || Object.keys(intel).length === 0) {
                  return (
                    <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
                      <Search className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
                      <h3 className="font-semibold text-sm">No company intelligence yet</h3>
                      <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                        Company intel is gathered during application generation. Enter a company name and generate to see results.
                      </p>
                    </div>
                  );
                }

                const overview = intel.company_overview || {};
                const culture = intel.culture_and_values || {};
                const tech = intel.tech_and_tools || {};
                const news = intel.recent_news || {};
                const strategy = intel.application_strategy || {};
                const competitive = intel.competitive_position || {};
                const confidence = intel.confidence || "unknown";

                return (
                  <div className="space-y-4">
                    {/* Confidence badge */}
                    <div className="flex items-center gap-2">
                      <div className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider ${
                        confidence === "high" ? "bg-emerald-500/10 text-emerald-600" :
                        confidence === "medium" ? "bg-amber-500/10 text-amber-600" :
                        "bg-zinc-500/10 text-zinc-500"
                      }`}>
                        <Shield className="h-3 w-3" />
                        {confidence} confidence intel
                      </div>
                      {intel.data_sources?.length > 0 && (
                        <span className="text-[10px] text-muted-foreground">
                          Sources: {intel.data_sources.join(", ")}
                        </span>
                      )}
                    </div>

                    {/* Company Overview */}
                    <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                      <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                        <Building2 className="h-4 w-4 text-primary" /> Company Overview
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {overview.industry && <div><span className="text-[10px] text-muted-foreground block">Industry</span><span className="text-sm font-medium">{overview.industry}</span></div>}
                        {overview.size && <div><span className="text-[10px] text-muted-foreground block">Size</span><span className="text-sm font-medium">{overview.size}</span></div>}
                        {overview.founded && <div><span className="text-[10px] text-muted-foreground block">Founded</span><span className="text-sm font-medium">{overview.founded}</span></div>}
                        {overview.headquarters && <div><span className="text-[10px] text-muted-foreground block">HQ</span><span className="text-sm font-medium">{overview.headquarters}</span></div>}
                      </div>
                      {overview.description && <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{overview.description}</p>}
                    </div>

                    {/* Culture & Values */}
                    {(culture.core_values?.length > 0 || culture.work_culture || culture.mission_statement) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Users className="h-4 w-4 text-violet-500" /> Culture & Values
                        </h3>
                        {culture.mission_statement && <p className="text-sm italic text-muted-foreground mb-3">&ldquo;{culture.mission_statement}&rdquo;</p>}
                        {culture.work_culture && <p className="text-sm text-muted-foreground mb-2"><strong>Work culture:</strong> {culture.work_culture}</p>}
                        {culture.core_values?.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {culture.core_values.map((v: string, i: number) => (
                              <span key={i} className="rounded-full bg-violet-500/10 px-2.5 py-0.5 text-[10px] font-medium text-violet-600">{v}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tech & Tools */}
                    {(tech.tech_stack?.length > 0 || tech.products?.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Globe className="h-4 w-4 text-cyan-500" /> Tech Stack & Products
                        </h3>
                        {tech.tech_stack?.length > 0 && (
                          <div className="mb-3">
                            <span className="text-[10px] text-muted-foreground block mb-1.5">Technologies</span>
                            <div className="flex flex-wrap gap-1.5">
                              {tech.tech_stack.map((t: string, i: number) => (
                                <span key={i} className="rounded-lg bg-cyan-500/10 px-2 py-0.5 text-[10px] font-mono text-cyan-600">{t}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {tech.products?.length > 0 && (
                          <div>
                            <span className="text-[10px] text-muted-foreground block mb-1.5">Products</span>
                            <div className="flex flex-wrap gap-1.5">
                              {tech.products.map((p: string, i: number) => (
                                <span key={i} className="rounded-lg bg-muted px-2 py-0.5 text-[10px] font-medium">{p}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Recent News */}
                    {(news.highlights?.length > 0 || news.growth_signals?.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Newspaper className="h-4 w-4 text-amber-500" /> Recent News & Growth
                        </h3>
                        {news.highlights?.map((h: string, i: number) => (
                          <div key={i} className="flex items-start gap-2 mb-2">
                            <TrendingUp className="h-3 w-3 text-amber-500 mt-1 shrink-0" />
                            <p className="text-sm text-muted-foreground">{h}</p>
                          </div>
                        ))}
                        {news.growth_signals?.map((g: string, i: number) => (
                          <div key={`g${i}`} className="flex items-start gap-2 mb-2">
                            <Sparkles className="h-3 w-3 text-emerald-500 mt-1 shrink-0" />
                            <p className="text-sm text-muted-foreground">{g}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Application Strategy — the golden section */}
                    {(strategy.keywords_to_use?.length > 0 || strategy.things_to_mention?.length > 0) && (
                      <div className="rounded-2xl border-2 border-primary/20 bg-primary/[0.02] p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Lightbulb className="h-4 w-4 text-primary" /> Application Strategy
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                          {strategy.keywords_to_use?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Keywords to include</span>
                              <div className="flex flex-wrap gap-1">
                                {strategy.keywords_to_use.map((k: string, i: number) => (
                                  <span key={i} className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">{k}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {strategy.values_to_emphasize?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Values to emphasize</span>
                              <div className="flex flex-wrap gap-1">
                                {strategy.values_to_emphasize.map((v: string, i: number) => (
                                  <span key={i} className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">{v}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {strategy.things_to_mention?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Mention in cover letter</span>
                              <ul className="space-y-1">
                                {strategy.things_to_mention.map((t: string, i: number) => (
                                  <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                                    <Sparkles className="h-2.5 w-2.5 text-primary mt-1 shrink-0" />{t}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {strategy.interview_topics?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Interview preparation</span>
                              <ul className="space-y-1">
                                {strategy.interview_topics.map((t: string, i: number) => (
                                  <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                                    <Target className="h-2.5 w-2.5 text-amber-500 mt-1 shrink-0" />{t}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                        {strategy.things_to_avoid?.length > 0 && (
                          <div className="mt-3 pt-3 border-t">
                            <span className="text-[10px] text-destructive/80 block mb-1 uppercase font-semibold">Avoid</span>
                            <div className="flex flex-wrap gap-1">
                              {strategy.things_to_avoid.map((a: string, i: number) => (
                                <span key={i} className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">{a}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Competitive Position */}
                    {(competitive.competitors?.length > 0 || competitive.differentiators?.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <BarChart3 className="h-4 w-4 text-blue-500" /> Competitive Landscape
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                          {competitive.competitors?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5">Competitors</span>
                              <div className="flex flex-wrap gap-1.5">
                                {competitive.competitors.map((c: string, i: number) => (
                                  <span key={i} className="rounded-lg bg-muted px-2 py-0.5 text-[10px] font-medium">{c}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {competitive.differentiators?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5">What makes them unique</span>
                              <ul className="space-y-1">
                                {competitive.differentiators.map((d: string, i: number) => (
                                  <li key={i} className="text-xs text-muted-foreground">{d}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
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
                                  toast({ title: "Export failed", description: "Could not generate PDF.", variant: "error" });
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
                        <div className="mx-auto max-w-[800px]">
                          <div
                            className="doc-preview"
                            dangerouslySetInnerHTML={{ __html: sanitizeHtml((app.benchmark as any).benchmarkCvHtml || "") }}
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

                {/* Benchmark Documents — Perfect 100% Application */}
                {app.benchmarkDocuments && Object.keys(app.benchmarkDocuments).length > 0 && (
                  <div className="mt-6">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
                        <Target className="h-4 w-4 text-emerald-500" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold">Perfect Application Documents</p>
                        <p className="text-xs text-muted-foreground">100% match benchmark — use as reference to improve yours</p>
                      </div>
                      <Badge variant="outline" className="ml-auto text-[10px] border-emerald-500/30 text-emerald-500">
                        {Object.keys(app.benchmarkDocuments).length} documents
                      </Badge>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {Object.entries(app.benchmarkDocuments).map(([key, html]) => {
                        if (!html) return null;
                        const docInfo = (app.discoveredDocuments || []).find((d: any) => d.key === key);
                        const label = docInfo?.label || key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                        return (
                          <details key={key} className="rounded-xl border bg-card/50 overflow-hidden group">
                            <summary className="px-4 py-2.5 flex items-center gap-2 cursor-pointer list-none select-none hover:bg-muted/30 transition-colors">
                              <FileText className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                              <span className="text-xs font-medium flex-1">{label}</span>
                              <span className="text-[9px] text-emerald-500 font-mono">100%</span>
                            </summary>
                            <div className="border-t p-4 max-h-[400px] overflow-y-auto">
                              <div className="prose prose-sm dark:prose-invert max-w-none text-xs" dangerouslySetInnerHTML={{ __html: html }} />
                            </div>
                          </details>
                        );
                      })}
                    </div>
                  </div>
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
                      <div className="mt-2 space-y-2">
                        {(app.gaps.recommendations ?? []).map((r: any, i: number) => {
                          const label = toLabel(r);
                          const priority = typeof r === "object" ? r?.priority : undefined;
                          return (
                            <div key={label || i} className="flex items-start gap-2">
                              <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${priority <= 1 ? "bg-rose-500" : priority <= 3 ? "bg-amber-500" : "bg-blue-500"}`} />
                              <span className="text-sm text-foreground/80 leading-relaxed">{label}</span>
                            </div>
                          );
                        })}
                      </div>
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
                      {(app.learningPlan.plan ?? []).map((w: any, idx: number) => (
                        <div key={w.week ?? idx} className="rounded-2xl border bg-card p-4 hover:shadow-soft-sm transition-shadow">
                          <div className="flex items-center gap-2">
                            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary text-xs font-bold shrink-0">
                              W{w.week ?? idx + 1}
                            </div>
                            <div className="text-sm font-semibold truncate">{w.theme ?? `Week ${w.week ?? idx + 1}`}</div>
                          </div>
                          <div className="mt-3 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">Outcomes</div>
                          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                            {(w.outcomes ?? w.goals ?? []).map((o: any, i: number) => {
                              const label = toLabel(o);
                              return <li key={label || i} className="flex items-start gap-1.5"><span className="text-emerald-500 mt-0.5">✓</span> {label}</li>;
                            })}
                          </ul>
                          <div className="mt-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Tasks</div>
                          <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                            {(w.tasks ?? []).map((t: any, i: number) => {
                              const label = toLabel(t);
                              return <li key={label || i} className="flex items-start gap-1.5"><span className="text-primary">→</span> {label}</li>;
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

            {/* Dynamic extra document tab content panels */}
            {app.generatedDocuments && Object.entries(app.generatedDocuments).map(([key, html]) => {
              if (!html) return null;
              const docInfo = (app.discoveredDocuments || []).find((d: any) => d.key === key);
              const label = docInfo?.label || key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
              const benchmarkHtml = app.benchmarkDocuments?.[key] || "";
              return (
                <TabsContent key={key} value={`extra-${key}`} className="mt-4">
                  <div className="space-y-4">
                    {/* Document info */}
                    {docInfo?.reason && (
                      <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-3 flex items-start gap-2">
                        <Sparkles className="h-4 w-4 text-teal-500 shrink-0 mt-0.5" />
                        <div>
                          <p className="text-xs font-semibold text-teal-600 dark:text-teal-400">AI-Discovered Document</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{docInfo.reason}</p>
                        </div>
                      </div>
                    )}

                    {/* Document content */}
                    <div className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden">
                      <div className="border-b bg-muted/20 px-5 py-3 flex items-center justify-between">
                        <h3 className="text-sm font-semibold">{label}</h3>
                        <div className="flex items-center gap-2">
                          {benchmarkHtml && (
                            <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-500">
                              Benchmark available
                            </Badge>
                          )}
                          <Badge variant="secondary" className="text-[10px]">
                            {docInfo?.priority || "standard"}
                          </Badge>
                        </div>
                      </div>
                      <div className="p-5">
                        <div
                          className="prose prose-sm dark:prose-invert max-w-none"
                          dangerouslySetInnerHTML={{ __html: html }}
                        />
                      </div>
                    </div>

                    {/* Benchmark comparison */}
                    {benchmarkHtml && (
                      <details className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden group">
                        <summary className="px-5 py-3 border-b bg-emerald-500/5 flex items-center gap-2 cursor-pointer list-none select-none">
                          <Target className="h-4 w-4 text-emerald-500" />
                          <span className="text-sm font-semibold">Benchmark Version (100% Match)</span>
                          <span className="text-xs text-muted-foreground ml-auto">Click to compare</span>
                        </summary>
                        <div className="p-5">
                          <div
                            className="prose prose-sm dark:prose-invert max-w-none opacity-90"
                            dangerouslySetInnerHTML={{ __html: benchmarkHtml }}
                          />
                        </div>
                      </details>
                    )}
                  </div>
                </TabsContent>
              );
            })}

            {/* ── Optional Documents Available for Generation ── */}
            {(() => {
              const generated = app.generatedDocuments || {};
              const coreKeys = new Set(["cv", "cover_letter", "personal_statement", "portfolio"]);
              const ungeneratedDocs = (app.discoveredDocuments || []).filter(
                (d: any) => d.key && !generated[d.key] && !coreKeys.has(d.key)
              );
              if (ungeneratedDocs.length === 0) return null;
              return (
                <TabsContent value="optional-docs" className="mt-4">
                  <div className="rounded-2xl border bg-card p-5 shadow-soft-sm space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-teal-500" />
                        Optional Documents
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        AI discovered these documents could strengthen your application. Generate them on demand.
                      </p>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {ungeneratedDocs.map((doc: any) => (
                        <div
                          key={doc.key}
                          className="rounded-xl border bg-muted/30 p-4 flex flex-col gap-2"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-medium truncate">{doc.label || doc.key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())}</p>
                              {doc.reason && (
                                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{doc.reason}</p>
                              )}
                            </div>
                            {doc.priority && (
                              <span className={`shrink-0 text-[10px] font-medium px-2 py-0.5 rounded-full ${
                                doc.priority === "high" ? "bg-amber-500/10 text-amber-600" :
                                doc.priority === "critical" ? "bg-red-500/10 text-red-600" :
                                "bg-muted text-muted-foreground"
                              }`}>
                                {doc.priority}
                              </span>
                            )}
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-2 rounded-xl self-start mt-1"
                            disabled={generatingDocKey === doc.key}
                            onClick={async () => {
                              if (!user) return;
                              setGeneratingDocKey(doc.key);
                              try {
                                const result = await generateOptionalDocument(appId, doc.key, doc.label || "");
                                // Update local app data so the new doc appears in tabs
                                if (result.html) {
                                  await patchApplication(appId, {
                                    generatedDocuments: { ...generated, [doc.key]: result.html },
                                  });
                                  toast({ title: "Document generated", description: `${doc.label || doc.key} is ready.` });
                                }
                              } catch (err: any) {
                                toast({ title: "Generation failed", description: err.message || "Please try again.", variant: "error" });
                              } finally {
                                setGeneratingDocKey(null);
                              }
                            }}
                          >
                            {generatingDocKey === doc.key ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Sparkles className="h-3.5 w-3.5" />
                            )}
                            {generatingDocKey === doc.key ? "Generating…" : "Generate"}
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                </TabsContent>
              );
            })()}

            {/* ── ATS Score Tab ── */}
            <TabsContent value="ats" className="mt-4">
              <ATSScorePanel cvHtml={cvLocal} jdText={app.confirmedFacts?.jdText || ""} />
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
                        toast({ title: "Export failed", description: "Could not generate ZIP.", variant: "error" });
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
                    gate={gatedDownload}
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
                    gate={gatedDownload}
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
                    gate={gatedDownload}
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
                    gate={gatedDownload}
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
                    gate={gatedDownload}
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
                    gate={gatedDownload}
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
                    Use &ldquo;Download All (ZIP)&rdquo; to get every document as a branded PDF + Word bundle — ready to attach to any application. Snapshot your versions before exporting to keep a history.
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4 lg:sticky lg:top-6 h-fit">
          {/* Agent Timeline Rail — replaces basic progress when stages are available */}
          {(agentState.isRunning || agentState.stages.length > 0) && (
            <div className="rounded-2xl border p-4 bg-card shadow-soft-sm">
              <AgentTimelineRail
                stages={agentState.stages}
                workflowState={agentState.workflowState}
                isRunning={agentState.isRunning}
              />
            </div>
          )}

          {/* Risk Panel — evidence strength, contradictions, ATS gaps */}
          {(agentState.finalAnalysis || agentState.evidenceSummary || (agentState.citations && agentState.citations.length > 0)) && (
            <div className="rounded-2xl border p-4 bg-card shadow-soft-sm">
              <RiskPanel
                finalAnalysis={agentState.finalAnalysis}
                evidenceSummary={agentState.evidenceSummary}
                citations={agentState.citations}
              />
            </div>
          )}

          {/* Evidence Inspector — claims, evidence links, fabrication flags */}
          {(agentState.citations || agentState.evidenceSummary) && (
            <div className="rounded-2xl border p-4 bg-card shadow-soft-sm">
              <EvidenceInspector
                citations={agentState.citations}
                evidenceSummary={agentState.evidenceSummary}
              />
            </div>
          )}

          {/* Validation Drawer — hard failures and soft warnings */}
          {agentState.validationReport && (
            <div className="rounded-2xl border p-4 bg-card shadow-soft-sm">
              <ValidationDrawer report={agentState.validationReport} />
            </div>
          )}

          {/* Quality Report */}
          {Object.keys(agentState.qualityScores).length > 0 && (
            <div className="rounded-2xl border p-4 bg-card shadow-soft-sm">
              <QualityReport
                scores={agentState.qualityScores}
                factCheck={agentState.factCheckSummary}
              />
            </div>
          )}

          {/* Replay Drawer — for failed or weak jobs */}
          <ReplayDrawer
            jobId={app?.id ?? null}
            jobStatus={regeneratingAll ? "running" : null}
            replayReport={agentState.replayReport}
            onRequestReplay={async (jobId) => {
              try {
                const token = session?.access_token;
                const res = await fetch(`/api/generate/jobs/${jobId}/replay`, {
                  headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) throw new Error(`Replay failed: ${res.status}`);
                const data = await res.json();
                setReplayReport(data.replay_report ?? null);
              } catch (e: any) {
                throw e;
              }
            }}
          />

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

      {/* Download gate modals */}
      <SignupModal open={showSignup} onOpenChange={setShowSignup} onSuccess={onSignupSuccess} />
    </div>
  );
}
