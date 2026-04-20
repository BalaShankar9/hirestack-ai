"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  FileText,
  GraduationCap,
  Layers,
  RefreshCw,
  Sparkles,
  Target,
  AlertTriangle,
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
  Library,
  Archive,
  CircleDot,
  ChevronDown,
  MessageSquare,
  DollarSign,
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
  getDocumentLibrary,
  generateDocumentInLibrary,
} from "@/lib/firestore";
import { useApplication, useEvidence, useTasks } from "@/lib/firestore";
import type { ModuleKey } from "@/lib/firestore";
import type { PipelineProgress } from "@/lib/firestore/ops";
import type { DocumentLibraryItem } from "@/lib/firestore/models";
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

import { CoachPanel } from "@/components/workspace/coach-panel";
import { ModuleCard } from "@/components/workspace/module-card";
import { TaskQueue } from "@/components/workspace/task-queue";
import { CommandSummary } from "@/components/workspace/command-summary";
import { NextBestAction } from "@/components/workspace/next-best-action";
import { DiagnosticScorecards } from "@/components/workspace/diagnostic-scorecards";
import { IntelligencePanel } from "@/components/workspace/intelligence-panel";
import { ReadinessTimeline } from "@/components/workspace/readiness-timeline";
import { KeywordChips } from "@/components/workspace/keyword-chips";
import { EvidencePicker } from "@/components/workspace/evidence-picker";
import { VersionHistoryDrawer } from "@/components/workspace/version-history-drawer";
import { DocEditorModule, ExportCard, EmptyState } from "@/components/workspace/doc-editor-module";
import type { DocMode } from "@/components/workspace/diff-toggle";
import { sanitizeHtml } from "@/lib/sanitize";
import { SectionErrorBoundary } from "@/components/error-boundary";
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
import { DocumentLibraryView } from "@/components/workspace/document-library-view";
import { DocumentUniverseGrid, type DocStatus } from "@/components/workspace/document-universe-grid";
import { WorkspaceKnowledgePanel } from "@/components/workspace/workspace-knowledge-panel";
import { DOCUMENT_UNIVERSE } from "@/lib/document-universe";
import { SignupModal } from "@/components/auth/signup-modal";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Safely coerce any DB value to a renderable string — handles both
 *  plain strings and legacy object shapes (e.g. {dimension, indicators}). */
function toLabel(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") {
    const obj = v as Record<string, unknown>;
    for (const k of ["dimension", "title", "name", "area", "description", "gap", "suggestion", "label"]) {
      if (typeof obj[k] === "string") return obj[k] as string;
    }
    return JSON.stringify(v);
  }
  return String(v ?? fallback);
}

function stripHtml(html: string) {
  return (html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/** Return up to `maxChars` plain-text characters from an HTML string for card previews. */
function htmlSnippet(html: string, maxChars = 120): string {
  const text = stripHtml(html);
  if (!text) return "";
  return text.length > maxChars ? text.slice(0, maxChars) + "…" : text;
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
  const { data: app, loading, error: appError } = useApplication(appId);
  const { data: evidence = [] } = useEvidence(userId, appId, 200);
  const { data: tasks = [], stats: taskStats } = useTasks(userId, appId, 200);

  const [tab, setTab] = useState(() => searchParams.get("tab") || "overview");
  const [cvMode, setCvMode] = useState<DocMode>("view");
  const [clMode, setClMode] = useState<DocMode>("view");
  const [psMode, setPsMode] = useState<DocMode>("view");
  const [portfolioMode, setPortfolioMode] = useState<DocMode>("view");
  const [resumeMode, setResumeMode] = useState<DocMode>("view");

  const cvEditorRef = useRef<any>(null);
  const clEditorRef = useRef<any>(null);
  const psEditorRef = useRef<any>(null);
  const portfolioEditorRef = useRef<any>(null);
  const resumeEditorRef = useRef<any>(null);
  const replayRef = useRef<HTMLDivElement>(null);
  const [cvEditor, setCvEditor] = useState<any>(null);
  const [clEditor, setClEditor] = useState<any>(null);
  const [psEditor, setPsEditor] = useState<any>(null);
  const [portfolioEditor, setPortfolioEditor] = useState<any>(null);
  const [resumeEditor, setResumeEditor] = useState<any>(null);
  const [autoInsertedEvidence, setAutoInsertedEvidence] = useState<string | null>(null);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<"cv" | "coverLetter" | "personalStatement" | "portfolio">("cv");

  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsTarget, setVersionsTarget] = useState<"cv" | "coverLetter" | "personalStatement" | "portfolio">("cv");

  const [cvLocal, setCvLocal] = useState<string>("");
  const [clLocal, setClLocal] = useState<string>("");
  const [psLocal, setPsLocal] = useState<string>("");
  const [portfolioLocal, setPortfolioLocal] = useState<string>("");
  const [resumeLocal, setResumeLocal] = useState<string>("");

  const [exporting, setExporting] = useState(false);
  const [regeneratingModule, setRegeneratingModule] = useState<string | null>(null);
  const [regeneratingAll, setRegeneratingAll] = useState(false);
  const [regenConfirm, setRegenConfirm] = useState<{ module: ModuleKey; label: string } | null>(null);
  const [liveProgress, setLiveProgress] = useState<number>(0);
  const [generatingDocKey, setGeneratingDocKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [docLibrary, setDocLibrary] = useState<Record<string, DocumentLibraryItem[]>>({});
  const [docLibraryLoading, setDocLibraryLoading] = useState(false);
  const { state: agentState, subscribe: agentSubscribe, handleAgentEvent, handleComplete, handleError: handleAgentError, reset: agentReset, setReplayReport } = useAgentStatus();

  // Auto-clear save indicator
  useEffect(() => {
    if (saveStatus === "saved" || saveStatus === "error") {
      const t = setTimeout(() => setSaveStatus("idle"), 2000);
      return () => clearTimeout(t);
    }
  }, [saveStatus]);

  // ⌘D keyboard shortcut for download
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "d") {
        e.preventDefault();
        const dlBtn = document.querySelector("[data-download-all]") as HTMLButtonElement | null;
        if (dlBtn && !dlBtn.disabled) dlBtn.click();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch document library when the library tab is selected
  const fetchDocLibrary = useCallback(async (silent = false) => {
    if (!appId) return;
    if (!silent) setDocLibraryLoading(true);
    try {
      const grouped = await getDocumentLibrary(appId);
      setDocLibrary(grouped);
    } catch { /* ignore */ } finally {
      if (!silent) setDocLibraryLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    if (tab === "library") fetchDocLibrary();
  }, [tab, fetchDocLibrary]);

  // Poll while any document is still generating
  useEffect(() => {
    if (tab !== "library") return;
    const hasGenerating = Object.values(docLibrary).flat().some(d => d.status === "generating");
    if (!hasGenerating) return;
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void fetchDocLibrary(true);
    }, 4000);
    return () => clearInterval(interval);
  }, [tab, docLibrary, fetchDocLibrary]);

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
    setResumeLocal(app.resumeHtml || "");
  }, [app, app?.cvHtml, app?.coverLetterHtml, app?.personalStatementHtml, app?.portfolioHtml, app?.resumeHtml]);

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

  useEffect(() => {
    if (!appRef.current) return;
    const t = setTimeout(() => {
      if (resumeLocal !== (appRef.current?.resumeHtml || "")) {
        setSaveStatus("saving");
        patchApplication(appId, { resumeHtml: resumeLocal }).then(() => setSaveStatus("saved")).catch(() => setSaveStatus("error"));
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, resumeLocal]);

  const keywords = useMemo(() => app?.benchmark?.keywords ?? [], [app?.benchmark?.keywords]);
  const missing = useMemo(() => app?.gaps?.missingKeywords ?? [], [app?.gaps?.missingKeywords]);

  // Pre-strip HTML once per content change — avoids re-stripping per keyword per render
  const strippedCv = useMemo(() => stripHtml(cvLocal).toLowerCase(), [cvLocal]);
  const strippedCl = useMemo(() => stripHtml(clLocal).toLowerCase(), [clLocal]);
  const strippedPs = useMemo(() => stripHtml(psLocal).toLowerCase(), [psLocal]);
  const strippedPortfolio = useMemo(() => stripHtml(portfolioLocal).toLowerCase(), [portfolioLocal]);
  const strippedResume = useMemo(() => stripHtml(resumeLocal).toLowerCase(), [resumeLocal]);

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
        return { ...a, onClick: () => { replayRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); } };
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
    // Show confirmation before firing a costly AI call
    const moduleLabel: Record<string, string> = {
      benchmark: "Company Benchmark", gaps: "Gap Analysis", cv: "CV", coverLetter: "Cover Letter",
      personalStatement: "Personal Statement", portfolio: "Portfolio", learningPlan: "Learning Plan",
    };
    setRegenConfirm({ module, label: moduleLabel[module] ?? module });
  };

  const doRegenerate = async (module: ModuleKey) => {
    if (!user || !app) return;
    setRegenConfirm(null);
    setRegeneratingModule(module);
    try {
      await regenerateModule({
        userId: user.uid,
        appId,
        module,
        evidenceCount: evidence.length,
      });
      toast.success("Regenerated!", `${moduleLabel[module] ?? module} has been regenerated with fresh AI content.`);
    } catch (err: any) {
      toast.error("Regeneration failed", err?.message ?? "Make sure the backend is running and try again.");
    } finally {
      setRegeneratingModule(null);
    }
  };

  const moduleLabel: Record<string, string> = {
    benchmark: "Company Benchmark", gaps: "Gap Analysis", cv: "CV", coverLetter: "Cover Letter",
    personalStatement: "Personal Statement", portfolio: "Portfolio", learningPlan: "Learning Plan",
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

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-48 rounded-xl" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-9 w-28 rounded-xl" />
            <Skeleton className="h-9 w-9 rounded-xl" />
          </div>
        </div>
        <Skeleton className="h-28 w-full rounded-2xl" />
        <Skeleton className="h-10 w-96 rounded-xl" />
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <div className="space-y-4">
            <Skeleton className="h-[240px] w-full rounded-2xl" />
            <Skeleton className="h-[180px] w-full rounded-2xl" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-[160px] w-full rounded-2xl" />
            <Skeleton className="h-[120px] w-full rounded-2xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!app && appError) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-4 text-center">
        <AlertCircle className="h-12 w-12 text-destructive/50" />
        <div>
          <h2 className="text-lg font-semibold">Failed to load application</h2>
          <p className="mt-1 text-sm text-muted-foreground max-w-md">
            We couldn&apos;t fetch this application. This may be a temporary network issue.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="default" onClick={() => window.location.reload()}>
            Try again
          </Button>
          <Button variant="outline" onClick={() => router.push("/dashboard")}>
            Back to dashboard
          </Button>
        </div>
      </div>
    );
  }

  if (!app) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-4 text-center">
        <FileText className="h-12 w-12 text-muted-foreground/50" />
        <div>
          <h2 className="text-lg font-semibold">Application not found</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            This application may have been deleted or you don&apos;t have access.
          </p>
        </div>
        <Button variant="outline" onClick={() => router.push("/dashboard")}>
          Back to dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <CommandSummary
            title={title}
            subtitle={subtitle}
            scores={app.scores}
            gapCount={missing.length}
            evidenceCount={evidence.length}
            modulesCompleted={
              (["benchmark", "gaps", "learningPlan", "cv", "coverLetter", "personalStatement", "portfolio"] as const)
                .filter((k) => app.modules[k]?.state === "ready").length
            }
            modulesTotal={7}
            factsLocked={!!app.factsLocked}
            updatedAt={app.updatedAt}
          />
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {saveStatus === "saving" && <span className="text-xs text-muted-foreground animate-pulse">Saving…</span>}
          {saveStatus === "saved" && <span className="text-xs text-emerald-500">Saved</span>}
          {saveStatus === "error" && <span className="text-xs text-destructive">Save failed</span>}

          {/* Status dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5 rounded-xl text-xs" aria-label="Application status">
                <CircleDot className={cn("h-3 w-3",
                  app.status === "active" ? "text-emerald-500" :
                  app.status === "draft" ? "text-amber-500" :
                  "text-muted-foreground"
                )} />
                {app.status === "active" ? "Active" : app.status === "draft" ? "Draft" : "Archived"}
                <ChevronDown className="h-3 w-3 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              {(["draft", "active", "archived"] as const).filter(s => s !== app.status).map(s => (
                <DropdownMenuItem key={s} onClick={async () => {
                  try {
                    await patchApplication(appId, { status: s });
                    toast({ title: `Marked as ${s}` });
                  } catch {
                    toast({ title: "Failed to update status", variant: "error" });
                  }
                }}>
                  <CircleDot className={cn("mr-2 h-3.5 w-3.5",
                    s === "active" ? "text-emerald-500" :
                    s === "draft" ? "text-amber-500" :
                    "text-muted-foreground"
                  )} />
                  {s === "active" ? "Mark Active" : s === "draft" ? "Mark Draft" : "Archive"}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            variant="default"
            size="sm"
            className="gap-2 rounded-xl shadow-glow-sm"
            disabled={exporting}
            data-download-all
            aria-label="Download all application documents as ZIP"
            onClick={async () => {
              if (!user) return;
              setExporting(true);
              try {
                await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: "zip_all", source: "header" } });
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
                toast({ title: "Documents downloaded", description: "Your application package is ready to submit." });
              } catch {
                toast({ title: "Export failed", description: "Could not generate ZIP.", variant: "error" });
              } finally {
                setExporting(false);
              }
            }}
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Download All
          </Button>
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
            {/* ── Flat Tab Navigation ── */}
            {(() => {
              const tailoredTabs = ["cv", "resume", "cover", "statement", "portfolio"];
              const benchmarkTabs = ["bench-cv", "bench-resume", "bench-cl", "bench-ps", "bench-portfolio", "bench-exec-summary", "bench-analysis", "bench-all"];
              const extraDocKeys = app.generatedDocuments ? Object.keys(app.generatedDocuments).filter(k => app.generatedDocuments![k]) : [];
              const generated = app.generatedDocuments || {};
              const coreKeys = new Set(["cv", "cover_letter", "personal_statement", "portfolio"]);
              const hasUngenerated = (app.discoveredDocuments || []).some(
                (d: any) => d.key && !generated[d.key] && !coreKeys.has(d.key)
              );
              const isTailoredActive = tailoredTabs.includes(tab) || tab.startsWith("extra-") || tab === "optional-docs" || tab === "all-docs";
              const isBenchmarkActive = tab === "benchmark" || benchmarkTabs.includes(tab);

              const triggerCls = "gap-1.5 rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm";
              const subTriggerCls = "gap-1.5 text-xs rounded-md data-[state=active]:bg-background data-[state=active]:shadow-sm";

              return (
                <div className="space-y-2">
                  {/* Primary flat navigation */}
                  <TabsList className="w-full justify-start overflow-x-auto h-auto gap-1 bg-muted/50 p-1 rounded-xl">
                    <TabsTrigger value="overview" className={triggerCls}><LayoutGrid className="h-3.5 w-3.5" />Overview</TabsTrigger>
                    {/* Benchmark group — custom button since it maps to multiple sub-tab values */}
                    <button
                      type="button"
                      role="tab"
                      className={cn(
                        "inline-flex items-center gap-1.5 whitespace-nowrap px-3 py-1.5 text-sm font-medium rounded-lg transition-all",
                        isBenchmarkActive
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground hover:bg-background/50"
                      )}
                      onClick={() => { if (!isBenchmarkActive) setTab("bench-cv"); }}
                    >
                      <Target className="h-3.5 w-3.5" />Benchmark
                    </button>
                    <TabsTrigger value="gaps" className={triggerCls}><BarChart3 className="h-3.5 w-3.5" />Skills & Gaps</TabsTrigger>
                    <TabsTrigger value="learning" className={triggerCls}><GraduationCap className="h-3.5 w-3.5" />Learning</TabsTrigger>
                    {/* Tailored group — custom button since it maps to multiple sub-tab values */}
                    <button
                      type="button"
                      role="tab"
                      className={cn(
                        "inline-flex items-center gap-1.5 whitespace-nowrap px-3 py-1.5 text-sm font-medium rounded-lg transition-all",
                        isTailoredActive
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground hover:bg-background/50"
                      )}
                      onClick={() => { if (!isTailoredActive) setTab("cv"); }}
                    >
                      <FileText className="h-3.5 w-3.5" />Tailored Docs
                    </button>
                    <TabsTrigger value="intel" className={triggerCls}><Search className="h-3.5 w-3.5" />Intel</TabsTrigger>
                    <TabsTrigger value="ats" className={triggerCls}><FileSearch className="h-3.5 w-3.5" />ATS Score</TabsTrigger>
                    <TabsTrigger value="library" className={triggerCls}><Library className="h-3.5 w-3.5" />Knowledge</TabsTrigger>
                    <TabsTrigger value="export" className={triggerCls}><Package className="h-3.5 w-3.5" />Export</TabsTrigger>
                  </TabsList>

                  {/* Benchmark document sub-tabs */}
                  {isBenchmarkActive && (
                    <TabsList className="w-full justify-start overflow-x-auto h-auto gap-1 bg-muted/30 p-1 rounded-lg">
                      <TabsTrigger value="bench-cv" className={subTriggerCls}><FileText className="h-3 w-3" />Benchmark CV</TabsTrigger>
                      <TabsTrigger value="bench-resume" className={subTriggerCls}><FileText className="h-3 w-3" />Resume</TabsTrigger>
                      <TabsTrigger value="bench-cl" className={subTriggerCls}><FileText className="h-3 w-3" />Cover Letter</TabsTrigger>
                      <TabsTrigger value="bench-ps" className={subTriggerCls}><PenTool className="h-3 w-3" />Personal Statement</TabsTrigger>
                      <TabsTrigger value="bench-portfolio" className={subTriggerCls}><FolderOpen className="h-3 w-3" />Portfolio</TabsTrigger>
                      <TabsTrigger value="bench-exec-summary" className={subTriggerCls}><FileText className="h-3 w-3" />Executive Summary</TabsTrigger>
                      <TabsTrigger value="bench-analysis" className={subTriggerCls}><BarChart3 className="h-3 w-3" />Analysis</TabsTrigger>
                      <TabsTrigger value="bench-all" className={subTriggerCls}><Layers className="h-3 w-3" />All Documents</TabsTrigger>
                    </TabsList>
                  )}

                  {/* Tailored document sub-tabs */}
                  {isTailoredActive && (
                    <TabsList className="w-full justify-start overflow-x-auto h-auto gap-1 bg-muted/30 p-1 rounded-lg">
                      <TabsTrigger value="cv" className={subTriggerCls}><FileText className="h-3 w-3" />CV</TabsTrigger>
                      <TabsTrigger value="resume" className={subTriggerCls}><FileText className="h-3 w-3" />Resume</TabsTrigger>
                      <TabsTrigger value="cover" className={subTriggerCls}><FileText className="h-3 w-3" />Cover Letter</TabsTrigger>
                      <TabsTrigger value="statement" className={subTriggerCls}><PenTool className="h-3 w-3" />Statement</TabsTrigger>
                      <TabsTrigger value="portfolio" className={subTriggerCls}><FolderOpen className="h-3 w-3" />Portfolio</TabsTrigger>
                      {extraDocKeys.map((key) => {
                        const docInfo = (app.discoveredDocuments || []).find((d: any) => d.key === key);
                        const label = docInfo?.label || key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                        return (
                          <TabsTrigger key={key} value={`extra-${key}`} className={subTriggerCls}>
                            <Sparkles className="h-3 w-3 text-teal-500" />
                            <span>{label}</span>
                          </TabsTrigger>
                        );
                      })}
                      {hasUngenerated && (
                        <TabsTrigger value="optional-docs" className={subTriggerCls}>
                          <Sparkles className="h-3 w-3 text-amber-500" />
                          <span>More Docs</span>
                        </TabsTrigger>
                      )}
                      <TabsTrigger value="all-docs" className={subTriggerCls}>
                        <Layers className="h-3 w-3" />
                        <span>All Documents</span>
                      </TabsTrigger>
                    </TabsList>
                  )}
                </div>
              );
            })()}

            <TabsContent value="overview" className="mt-4">
              <SectionErrorBoundary label="Mission Control">
              <div className="space-y-5">

              {/* ── Failed Modules Banner ── */}
              {(() => {
                const moduleLabels: Record<string, string> = {
                  benchmark: "Benchmark", gaps: "Skills & Gaps", learningPlan: "Learning Plan",
                  cv: "Tailored CV", coverLetter: "Cover Letter", personalStatement: "Personal Statement",
                  portfolio: "Portfolio", scorecard: "Scorecard",
                };
                const failedMods = Object.entries(app?.modules ?? {})
                  .filter(([, v]) => (v as any)?.state === "error")
                  .map(([k]) => k);
                if (failedMods.length === 0) return null;
                return (
                  <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-4">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                          {failedMods.length === 1 ? "1 module needs attention" : `${failedMods.length} modules need attention`}
                        </h4>
                        <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
                          {failedMods.map(k => moduleLabels[k] ?? k).join(", ")} didn&apos;t generate successfully. You can retry individually or regenerate everything.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {failedMods.map(k => (
                            <Button key={k} variant="outline" size="sm" className="h-7 gap-1.5 rounded-lg text-xs border-amber-300 dark:border-amber-700" onClick={() => regenerate(k as ModuleKey)} disabled={regeneratingModule === k || regeneratingAll}>
                              <RefreshCw className="h-3 w-3" /> {moduleLabels[k] ?? k}
                            </Button>
                          ))}
                          {failedMods.length > 1 && (
                            <Button variant="default" size="sm" className="h-7 gap-1.5 rounded-lg text-xs" onClick={regenerateAll} disabled={regeneratingAll || !!regeneratingModule}>
                              {regeneratingAll ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                              Retry All Failed
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* ── Next Best Action ── */}
              {(() => {
                const sc = app.scores ?? {};
                const dims = [
                  { name: "Match", score: sc.match ?? 0 },
                  { name: "ATS Readiness", score: sc.atsReadiness ?? 0 },
                  { name: "6-Second Scan", score: sc.recruiterScan ?? 0 },
                  { name: "Evidence Strength", score: sc.evidenceStrength ?? 0 },
                ];
                const weakest = dims.filter(d => d.score > 0).sort((a, b) => a.score - b.score)[0];
                return (
                  <NextBestAction
                    topFix={typeof sc.topFix === "string" ? sc.topFix : undefined}
                    gapCount={missing.length}
                    weakestDimension={weakest?.name}
                    weakestScore={weakest?.score}
                    onNavigate={(t) => setTab(t)}
                  />
                );
              })()}

              {/* ── Diagnostic Scorecards ── */}
              <DiagnosticScorecards
                scores={app.scores}
                gaps={app.gaps}
                benchmark={app.benchmark}
                onNavigate={(t) => setTab(t)}
              />

              {/* ── Intelligence Panel + Readiness Timeline side by side on larger screens ── */}
              <div className="grid gap-4 lg:grid-cols-2">
                <IntelligencePanel
                  app={app}
                  keywordCount={keywords.length}
                  missingCount={missing.length}
                  evidenceCount={evidence.length}
                />
                <ReadinessTimeline app={app} evidenceCount={evidence.length} />
              </div>

              {/* ── Module Overview ── */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Modules</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2 rounded-xl"
                    onClick={regenerateAll}
                    disabled={regeneratingAll || !!regeneratingModule}
                  >
                    {regeneratingAll ? (
                      <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Regenerating…</>
                    ) : (
                      <><RefreshCw className="h-3.5 w-3.5" /> Regenerate All</>
                    )}
                  </Button>
                </div>

                {/* Analysis layer */}
                <div>
                  <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Analysis</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <ModuleCard
                      title="Benchmark"
                      description="Ideal candidate profile & scoring rubric"
                      status={modStatus("benchmark")}
                      icon={<Target className="h-5 w-5" />}
                      snippet={app.benchmark?.summary ? htmlSnippet(String(app.benchmark.summary)) : undefined}
                      onOpen={() => setTab("benchmark")}
                      onRegenerate={() => regenerate("benchmark")}
                    />
                    <ModuleCard
                      title="Skills & Gaps"
                      description="Compatibility score, missing keywords & fixes"
                      status={modStatus("gaps")}
                      icon={<Layers className="h-5 w-5" />}
                      snippet={app.gaps?.summary ? htmlSnippet(String(app.gaps.summary)) : undefined}
                      onOpen={() => setTab("gaps")}
                      onRegenerate={() => regenerate("gaps")}
                    />
                  </div>
                </div>

                {/* Tailored Documents layer — unified card */}
                <div>
                  <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Tailored Documents</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <ModuleCard
                      title="Tailored CV"
                      description="ATS-optimized, keyword-rich, strategically enhanced"
                      status={modStatus("cv")}
                      icon={<FileText className="h-5 w-5" />}
                      snippet={cvLocal ? htmlSnippet(cvLocal) : undefined}
                      onOpen={() => setTab("cv")}
                      onRegenerate={() => regenerate("cv")}
                    />
                    <ModuleCard
                      title="Cover Letter"
                      description="Evidence-backed narrative for this role"
                      status={modStatus("coverLetter")}
                      icon={<FileText className="h-5 w-5" />}
                      snippet={clLocal ? htmlSnippet(clLocal) : undefined}
                      onOpen={() => setTab("cover")}
                      onRegenerate={() => regenerate("coverLetter")}
                    />
                    <ModuleCard
                      title="Personal Statement"
                      description="Compelling motivation narrative"
                      status={modStatus("personalStatement")}
                      icon={<PenTool className="h-5 w-5" />}
                      snippet={psLocal ? htmlSnippet(psLocal) : undefined}
                      onOpen={() => setTab("statement")}
                      onRegenerate={() => regenerate("personalStatement")}
                    />
                    <ModuleCard
                      title="Portfolio & Evidence"
                      description="Project showcase with impact metrics"
                      status={modStatus("portfolio")}
                      icon={<FolderOpen className="h-5 w-5" />}
                      snippet={portfolioLocal ? htmlSnippet(portfolioLocal) : undefined}
                      onOpen={() => setTab("portfolio")}
                      onRegenerate={() => regenerate("portfolio")}
                    />
                  </div>
                </div>

                {/* Growth layer */}
                <div>
                  <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Growth</div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <ModuleCard
                      title="Learning Plan"
                      description="Sprint-based skill development roadmap"
                      status={modStatus("learningPlan")}
                      icon={<GraduationCap className="h-5 w-5" />}
                      snippet={app.learningPlan?.focus?.length ? htmlSnippet((app.learningPlan.focus as string[]).join(", ")) : undefined}
                      onOpen={() => setTab("learning")}
                      onRegenerate={() => regenerate("learningPlan")}
                    />
                  </div>
                </div>
              </div>

              {/* ── Action Queue ── */}
              <TaskQueue tasks={tasks} onToggle={onToggleTask} />

              </div>
              </SectionErrorBoundary>
            </TabsContent>

            {/* ── Intel Tab ── */}
            <TabsContent value="intel" className="mt-4">
              <SectionErrorBoundary label="Intel">
              {(() => {
                const intel = app?.companyIntel;
                if (!intel || Object.keys(intel).length === 0 || (intel.confidence === "low" && !intel.company_overview)) {
                  return (
                    <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
                      <Search className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
                      <h3 className="font-semibold text-sm">No company intelligence yet</h3>
                      <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                        Company intel is gathered during application generation. Enter a company name and generate to see results.
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-4 gap-2 rounded-xl"
                        onClick={regenerateAll}
                        disabled={regeneratingAll || !!regeneratingModule}
                      >
                        {regeneratingAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                        {regeneratingAll ? "Working…" : "Regenerate Application"}
                      </Button>
                    </div>
                  );
                }

                const overview = intel.company_overview || {};
                const culture = intel.culture_and_values || {};
                const tech = intel.tech_and_engineering || intel.tech_and_tools || {};
                const products = intel.products_and_services || {};
                const news = intel.recent_developments || intel.recent_news || {};
                const strategy = intel.application_strategy || {};
                const competitive = intel.market_position || intel.competitive_position || {};
                const confidence = intel.confidence || "unknown";
                const workCulture = culture.work_environment || culture.work_culture;
                const newsHighlights = Array.isArray(news.news_highlights || news.highlights) ? (news.news_highlights || news.highlights) : [];
                const growthSignals = Array.isArray(news.growth_signals) ? news.growth_signals : [];
                const interviewTopics = Array.isArray(strategy.interview_prep_topics || strategy.interview_topics) ? (strategy.interview_prep_topics || strategy.interview_topics) : [];
                const techStack = Array.isArray(tech.tech_stack || tech.programming_languages) ? (tech.tech_stack || tech.programming_languages) : [];
                const productList = Array.isArray(tech.products || products.main_products) ? (tech.products || products.main_products) : [];

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
                      {Array.isArray(intel.data_sources) && intel.data_sources.length > 0 && (
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
                    {(Array.isArray(culture.core_values) && culture.core_values.length > 0 || workCulture || culture.mission_statement) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Users className="h-4 w-4 text-violet-500" /> Culture & Values
                        </h3>
                        {culture.mission_statement && <p className="text-sm italic text-muted-foreground mb-3">&ldquo;{culture.mission_statement}&rdquo;</p>}
                        {workCulture && <p className="text-sm text-muted-foreground mb-2"><strong>Work culture:</strong> {workCulture}</p>}
                        {Array.isArray(culture.core_values) && culture.core_values.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {culture.core_values.map((v: string, i: number) => (
                              <span key={i} className="rounded-full bg-violet-500/10 px-2.5 py-0.5 text-[10px] font-medium text-violet-600">{v}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tech & Tools */}
                    {(techStack?.length > 0 || productList?.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Globe className="h-4 w-4 text-cyan-500" /> Tech Stack & Products
                        </h3>
                        {techStack?.length > 0 && (
                          <div className="mb-3">
                            <span className="text-[10px] text-muted-foreground block mb-1.5">Technologies</span>
                            <div className="flex flex-wrap gap-1.5">
                              {techStack.map((t: string, i: number) => (
                                <span key={i} className="rounded-lg bg-cyan-500/10 px-2 py-0.5 text-[10px] font-mono text-cyan-600">{t}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {productList?.length > 0 && (
                          <div>
                            <span className="text-[10px] text-muted-foreground block mb-1.5">Products</span>
                            <div className="flex flex-wrap gap-1.5">
                              {productList.map((p: string, i: number) => (
                                <span key={i} className="rounded-lg bg-muted px-2 py-0.5 text-[10px] font-medium">{p}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Recent News */}
                    {(newsHighlights?.length > 0 || growthSignals?.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Newspaper className="h-4 w-4 text-amber-500" /> Recent News & Growth
                        </h3>
                        {newsHighlights?.map((h: string, i: number) => (
                          <div key={i} className="flex items-start gap-2 mb-2">
                            <TrendingUp className="h-3 w-3 text-amber-500 mt-1 shrink-0" />
                            <p className="text-sm text-muted-foreground">{h}</p>
                          </div>
                        ))}
                        {growthSignals?.map((g: string, i: number) => (
                          <div key={`g${i}`} className="flex items-start gap-2 mb-2">
                            <Sparkles className="h-3 w-3 text-emerald-500 mt-1 shrink-0" />
                            <p className="text-sm text-muted-foreground">{g}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Application Strategy — the golden section */}
                    {(Array.isArray(strategy.keywords_to_use) && strategy.keywords_to_use.length > 0 || Array.isArray(strategy.things_to_mention) && strategy.things_to_mention.length > 0) && (
                      <div className="rounded-2xl border-2 border-primary/20 bg-primary/[0.02] p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <Lightbulb className="h-4 w-4 text-primary" /> Application Strategy
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                          {Array.isArray(strategy.keywords_to_use) && strategy.keywords_to_use.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Keywords to include</span>
                              <div className="flex flex-wrap gap-1">
                                {strategy.keywords_to_use.map((k: string, i: number) => (
                                  <span key={i} className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">{k}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {Array.isArray(strategy.values_to_emphasize) && strategy.values_to_emphasize.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Values to emphasize</span>
                              <div className="flex flex-wrap gap-1">
                                {strategy.values_to_emphasize.map((v: string, i: number) => (
                                  <span key={i} className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">{v}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {Array.isArray(strategy.things_to_mention) && strategy.things_to_mention.length > 0 && (
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
                          {interviewTopics?.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5 uppercase font-semibold">Interview preparation</span>
                              <ul className="space-y-1">
                                {interviewTopics.map((t: string, i: number) => (
                                  <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                                    <Target className="h-2.5 w-2.5 text-amber-500 mt-1 shrink-0" />{t}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                        {Array.isArray(strategy.things_to_avoid) && strategy.things_to_avoid.length > 0 && (
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
                    {(Array.isArray(competitive.competitors) && competitive.competitors.length > 0 || Array.isArray(competitive.differentiators) && competitive.differentiators.length > 0) && (
                      <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                        <h3 className="flex items-center gap-2 font-semibold text-sm mb-3">
                          <BarChart3 className="h-4 w-4 text-blue-500" /> Competitive Landscape
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                          {Array.isArray(competitive.competitors) && competitive.competitors.length > 0 && (
                            <div>
                              <span className="text-[10px] text-muted-foreground block mb-1.5">Competitors</span>
                              <div className="flex flex-wrap gap-1.5">
                                {competitive.competitors.map((c: string, i: number) => (
                                  <span key={i} className="rounded-lg bg-muted px-2 py-0.5 text-[10px] font-medium">{c}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {Array.isArray(competitive.differentiators) && competitive.differentiators.length > 0 && (
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
              </SectionErrorBoundary>
            </TabsContent>

            {/* ── Benchmark Sub-Tabs ──────────────────────────── */}
            {["bench-cv", "bench-resume", "bench-cl", "bench-ps", "bench-portfolio", "bench-exec-summary"].map((tabKey) => {
              const docMap: Record<string, { title: string; subtitle: string; field: string; tailoredField: string; filename: string; docType: "cv" | "coverLetter" | "personalStatement" | "portfolio" }> = {
                "bench-cv": {
                  title: "Benchmark CV",
                  subtitle: "A full reference CV — your name with benchmark-level experience. Read-only north star.",
                  field: "cv",
                  tailoredField: "cvHtml",
                  filename: "HireStack_Benchmark_CV",
                  docType: "cv",
                },
                "bench-resume": {
                  title: "Benchmark Resume",
                  subtitle: "The ideal US-style resume for this role — concise, achievement-driven, ATS-optimized.",
                  field: "resume",
                  tailoredField: "",
                  filename: "HireStack_Benchmark_Resume",
                  docType: "cv",
                },
                "bench-cl": {
                  title: "Benchmark Cover Letter",
                  subtitle: "The ideal cover letter for this role — reference quality to measure against.",
                  field: "cover_letter",
                  tailoredField: "coverLetterHtml",
                  filename: "HireStack_Benchmark_Cover_Letter",
                  docType: "coverLetter",
                },
                "bench-ps": {
                  title: "Benchmark Personal Statement",
                  subtitle: "The ideal personal statement — benchmark-quality motivation narrative.",
                  field: "personal_statement",
                  tailoredField: "personalStatementHtml",
                  filename: "HireStack_Benchmark_Personal_Statement",
                  docType: "personalStatement",
                },
                "bench-portfolio": {
                  title: "Benchmark Portfolio",
                  subtitle: "The ideal portfolio showcase — benchmark-quality project case studies.",
                  field: "portfolio",
                  tailoredField: "portfolioHtml",
                  filename: "HireStack_Benchmark_Portfolio",
                  docType: "portfolio",
                },
                "bench-exec-summary": {
                  title: "Benchmark Executive Summary",
                  subtitle: "The ideal executive summary — concise leadership snapshot for senior roles.",
                  field: "executive_summary",
                  tailoredField: "",
                  filename: "HireStack_Benchmark_Executive_Summary",
                  docType: "cv",
                },
              };
              const meta = docMap[tabKey]!;
              const benchDocs = app.benchmarkDocuments || {};
              const html = tabKey === "bench-cv"
                ? (benchDocs["cv"] || app.benchmark?.benchmarkCvHtml || "")
                : (benchDocs[meta.field] || "");
              const tailoredHtml = (app as any)[meta.tailoredField] || "";

              return (
                <TabsContent key={tabKey} value={tabKey} className="mt-4">
                  <SectionErrorBoundary label={meta.title}>
                  <div className="space-y-4">
                    <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold">{meta.title}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{meta.subtitle}</div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          {html && (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1.5 rounded-xl text-xs"
                                onClick={async () => {
                                  try {
                                    await downloadPdf(html, {
                                      filename: meta.filename,
                                      documentType: meta.docType,
                                    });
                                  } catch {
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
                                onClick={async () => {
                                  try {
                                    await downloadDocx(html, {
                                      filename: meta.filename,
                                      documentType: meta.docType,
                                    });
                                  } catch {
                                    toast({ title: "Export failed", description: "Could not generate Word doc.", variant: "error" });
                                  }
                                }}
                              >
                                <Download className="h-3.5 w-3.5" />
                                Word
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="gap-1.5 rounded-xl text-xs"
                                onClick={() => {
                                  navigator.clipboard.writeText(stripHtml(html));
                                  toast.success("Copied!", `${meta.title} text copied to clipboard.`);
                                }}
                              >
                                <ClipboardCopy className="h-3.5 w-3.5" />
                                Copy
                              </Button>
                            </>
                          )}
                          <Button variant="outline" size="sm" className="gap-2 rounded-xl" onClick={() => regenerate("benchmark")} disabled={regeneratingModule === "benchmark"}>
                            {regeneratingModule === "benchmark" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                            {regeneratingModule === "benchmark" ? "Working…" : "Regenerate"}
                          </Button>
                        </div>
                      </div>

                      <Separator className="my-4" />

                      {html ? (
                        <div className="mx-auto max-w-[800px]">
                          <div
                            className="doc-preview"
                            dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
                          />
                        </div>
                      ) : (
                        <EmptyState
                          title={`${meta.title} not generated yet.`}
                          body="Run the wizard generation or regenerate the benchmark module."
                          action={<Button onClick={() => regenerate("benchmark")} disabled={regeneratingModule === "benchmark"}>Generate benchmark</Button>}
                        />
                      )}

                      {/* Diff comparison with tailored version */}
                      {html && tailoredHtml && (
                        <details className="mt-4">
                          <summary className="cursor-pointer text-xs font-medium text-primary hover:underline">
                            Compare with your Tailored version
                          </summary>
                          <div className="mt-3 grid gap-4 md:grid-cols-2">
                            <div>
                              <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Benchmark (Target)</div>
                              <div className="rounded-lg border p-3 max-h-[400px] overflow-y-auto">
                                <div className="prose prose-sm dark:prose-invert max-w-none text-xs" dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }} />
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Your Tailored Version</div>
                              <div className="rounded-lg border p-3 max-h-[400px] overflow-y-auto">
                                <div className="prose prose-sm dark:prose-invert max-w-none text-xs" dangerouslySetInnerHTML={{ __html: sanitizeHtml(tailoredHtml) }} />
                              </div>
                            </div>
                          </div>
                        </details>
                      )}
                    </div>
                  </div>
                  </SectionErrorBoundary>
                </TabsContent>
              );
            })}

            {/* ── Benchmark Analysis Sub-Tab ──────────────────── */}
            <TabsContent value="bench-analysis" className="mt-4">
              <SectionErrorBoundary label="Benchmark Analysis">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">Benchmark — Ideal Candidate Analysis</div>
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

                    {app.benchmark.idealProfile && (
                      <div className="rounded-xl border p-4">
                        <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Ideal Candidate</div>
                        <div className="mt-2 text-base font-bold">{toLabel(app.benchmark.idealProfile?.title || app.benchmark.idealProfile?.name)}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {app.benchmark.idealProfile?.years_experience} yrs experience
                        </div>
                      </div>
                    )}

                    {(app.benchmark.idealSkills?.length ?? 0) > 0 && (
                      <div>
                        <div className="text-xs font-semibold mb-3">Key Skills Required</div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {(app.benchmark.idealSkills ?? []).slice(0, 8).map((s: any, i: number) => (
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
                  </div>
                ) : (
                  <EmptyState
                    title="Benchmark not generated yet."
                    body="Run the wizard generation or regenerate the module here."
                    action={<Button onClick={() => regenerate("benchmark")} disabled={regeneratingModule === "benchmark"}>Generate benchmark</Button>}
                  />
                )}
              </div>
              </SectionErrorBoundary>
            </TabsContent>

            {/* ── Benchmark All Documents Sub-Tab ─────────────── */}
            <TabsContent value="bench-all" className="mt-4">
              <SectionErrorBoundary label="Benchmark Documents">
              <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                {/* Legacy benchmarkDocuments not shown by sub-tabs (e.g. from on-demand gen) */}
                {(() => {
                  const benchDocs = app.benchmarkDocuments || {};
                  const shownKeys = new Set(["cv", "resume", "cover_letter", "personal_statement", "portfolio", "executive_summary"]);
                  const extraBenchDocs = Object.entries(benchDocs).filter(([k, html]) => html && !shownKeys.has(k));
                  if (extraBenchDocs.length === 0) return null;
                  return (
                    <div className="mb-6">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10">
                          <Target className="h-4 w-4 text-emerald-500" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold">Additional Benchmark Documents</p>
                          <p className="text-xs text-muted-foreground">On-demand benchmark documents — use as reference</p>
                        </div>
                        <Badge variant="outline" className="ml-auto text-[10px] border-emerald-500/30 text-emerald-500">
                          {extraBenchDocs.length} documents
                        </Badge>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {extraBenchDocs.map(([key, html]) => {
                          const docInfo = (app.discoveredDocuments || []).find((d: any) => d.key === key);
                          const label = docInfo?.label || key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                          return (
                            <div key={key} className="rounded-xl border bg-card/50 p-4">
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <FileText className="h-3.5 w-3.5 text-emerald-500" />
                                  <span className="text-xs font-semibold">{label}</span>
                                </div>
                                <div className="flex items-center gap-1">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0"
                                    onClick={async () => {
                                      try {
                                        await downloadPdf(html, { filename: `HireStack_Benchmark_${key}`, documentType: "cv" });
                                      } catch { toast({ title: "Export failed", variant: "error" }); }
                                    }}
                                  >
                                    <Download className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0"
                                    onClick={() => {
                                      navigator.clipboard.writeText(stripHtml(html));
                                      toast.success("Copied!", `${label} copied to clipboard.`);
                                    }}
                                  >
                                    <ClipboardCopy className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </div>
                              <div className="max-h-[300px] overflow-y-auto rounded-lg border p-3">
                                <div className="prose prose-sm dark:prose-invert max-w-none text-xs" dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <Separator className="my-5" />
                    </div>
                  );
                })()}

                <DocumentUniverseGrid
                  title="Benchmark Document Universe"
                  universe={DOCUMENT_UNIVERSE}
                  statusMap={(() => {
                    const m = new Map<string, DocStatus>();
                    const benchDocs = app.benchmarkDocuments || {};
                    for (const [key, html] of Object.entries(benchDocs)) {
                      if (html) m.set(key, { status: "ready", htmlContent: html });
                    }
                    if (app.benchmark?.benchmarkCvHtml) m.set("cv", { status: "ready", htmlContent: app.benchmark.benchmarkCvHtml });
                    return m;
                  })()}
                  onView={(key) => {
                    const benchDocs = app.benchmarkDocuments || {};
                    if (key === "cv") setTab("bench-cv");
                    else if (key === "resume" && benchDocs["resume"]) setTab("bench-resume");
                    else if (key === "cover_letter" && benchDocs["cover_letter"]) setTab("bench-cl");
                    else if (key === "personal_statement" && benchDocs["personal_statement"]) setTab("bench-ps");
                    else if (key === "portfolio" && benchDocs["portfolio"]) setTab("bench-portfolio");
                    else if (key === "executive_summary" && benchDocs["executive_summary"]) setTab("bench-exec-summary");
                  }}
                  onDownload={async (key) => {
                    const benchDocs = app.benchmarkDocuments || {};
                    const html = key === "cv" ? (benchDocs["cv"] || app.benchmark?.benchmarkCvHtml || "") : (benchDocs[key] || "");
                    if (!html) { toast({ title: "No content", description: "Document not generated yet.", variant: "error" }); return; }
                    try {
                      await downloadPdf(html, { filename: `HireStack_Benchmark_${key}`, documentType: "cv" });
                    } catch { toast({ title: "Export failed", variant: "error" }); }
                  }}
                  onGenerate={async (key, label) => {
                    try {
                      await generateDocumentInLibrary(key, "benchmark", appId, label);
                      toast({ title: "Generation started", description: `Generating benchmark ${label}…` });
                    } catch {
                      toast({ title: "Generation failed", variant: "error" });
                    }
                  }}
                />
              </div>
              </SectionErrorBoundary>
            </TabsContent>

            <TabsContent value="gaps" className="mt-4">
              <SectionErrorBoundary label="Gaps">
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
                    {app.gaps.compatibility != null && (
                      <div className="rounded-xl bg-gradient-to-br from-primary/5 to-violet-500/5 border border-primary/10 p-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-xs font-semibold text-primary">Compatibility Score</div>
                            <div className="mt-1 text-2xl font-bold">{app.gaps.compatibility}%</div>
                          </div>
                          <div className="text-right text-xs text-muted-foreground">
                            {app.gaps.compatibility >= 70 ? "Strong match" : app.gaps.compatibility >= 45 ? "Competitive" : "Needs work"}
                          </div>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full transition-all ${app.gaps.compatibility >= 70 ? "bg-emerald-500" : app.gaps.compatibility >= 45 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${app.gaps.compatibility}%` }} />
                        </div>
                        {toLabel(app.gaps.summary) && (
                          <div className="mt-3 text-sm text-foreground/80 leading-relaxed">{toLabel(app.gaps.summary)}</div>
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
              </SectionErrorBoundary>
            </TabsContent>

            <TabsContent value="learning" className="mt-4">
              <SectionErrorBoundary label="Learning">
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

                {app.learningPlan && (app.learningPlan.focus?.length || app.learningPlan.plan?.length || app.learningPlan.resources?.length) ? (
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
              </SectionErrorBoundary>
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
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 rounded-xl text-xs h-7"
                            onClick={async () => {
                              try {
                                await downloadPdf(html, { filename: `HireStack_${key}`, documentType: "cv" });
                              } catch { toast({ title: "Export failed", variant: "error" }); }
                            }}
                          >
                            <Download className="h-3 w-3" />
                            PDF
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5 rounded-xl text-xs h-7"
                            onClick={async () => {
                              try {
                                await downloadDocx(html, { filename: `HireStack_${key}`, documentType: "cv" });
                              } catch { toast({ title: "Export failed", variant: "error" }); }
                            }}
                          >
                            <Download className="h-3 w-3" />
                            Word
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="gap-1.5 rounded-xl text-xs h-7"
                            onClick={() => {
                              navigator.clipboard.writeText(stripHtml(html));
                              toast.success("Copied!", `${label} copied to clipboard.`);
                            }}
                          >
                            <ClipboardCopy className="h-3 w-3" />
                            Copy
                          </Button>
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
                          dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
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
                            dangerouslySetInnerHTML={{ __html: sanitizeHtml(benchmarkHtml) }}
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
                  <SectionErrorBoundary label="Optional Documents">
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
                  </SectionErrorBoundary>
                </TabsContent>
              );
            })()}

            {/* ── All Documents Universe sub-tab (Tailored) ── */}
            <TabsContent value="all-docs" className="mt-4">
              <SectionErrorBoundary label="All Documents">
                <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                  <DocumentUniverseGrid
                    title="Tailored Document Universe"
                    universe={DOCUMENT_UNIVERSE}
                    statusMap={(() => {
                      const m = new Map<string, DocStatus>();
                      // Core docs from inline state
                      if (app.cvHtml) m.set("cv", { status: "ready" });
                      if (app.coverLetterHtml) m.set("cover_letter", { status: "ready" });
                      if (app.personalStatementHtml) m.set("personal_statement", { status: "ready" });
                      if (app.portfolioHtml) m.set("portfolio", { status: "ready" });
                      // Discovered/generated extra docs
                      if (app.generatedDocuments) {
                        for (const [key, html] of Object.entries(app.generatedDocuments)) {
                          if (html) m.set(key, { status: "ready" });
                        }
                      }
                      // Discovered but ungenerated docs → planned
                      if (app.discoveredDocuments) {
                        for (const doc of app.discoveredDocuments as any[]) {
                          if (doc.key && !m.has(doc.key)) m.set(doc.key, { status: "planned" });
                        }
                      }
                      return m;
                    })()}
                    onView={(key) => {
                      const tabMap: Record<string, string> = {
                        cv: "cv", cover_letter: "cover", personal_statement: "statement", portfolio: "portfolio",
                      };
                      if (tabMap[key]) { setTab(tabMap[key]); return; }
                      if (app.generatedDocuments?.[key]) { setTab(`extra-${key}`); }
                    }}
                    onDownload={async (key) => {
                      const coreMap: Record<string, string> = {
                        cv: app.cvHtml || "", cover_letter: app.coverLetterHtml || "",
                        personal_statement: app.personalStatementHtml || "", portfolio: app.portfolioHtml || "",
                      };
                      const html = coreMap[key] ?? app.generatedDocuments?.[key] ?? "";
                      if (!html) { toast({ title: "No content", description: "Document not generated yet.", variant: "error" }); return; }
                      try {
                        await downloadPdf(html, { filename: `HireStack_${key}`, documentType: "cv" });
                      } catch { toast({ title: "Export failed", variant: "error" }); }
                    }}
                    onGenerate={async (key, label) => {
                      try {
                        await generateDocumentInLibrary(key, "tailored", appId, label);
                        toast({ title: "Generation started", description: `Generating ${label}…` });
                      } catch {
                        toast({ title: "Generation failed", variant: "error" });
                      }
                    }}
                  />
                </div>
              </SectionErrorBoundary>
            </TabsContent>

            {/* ── ATS Score Tab ── */}
            <TabsContent value="ats" className="mt-4">
              <SectionErrorBoundary label="ATS Score">
                <ATSScorePanel cvHtml={cvLocal} jdText={app.confirmedFacts?.jdText || ""} />
              </SectionErrorBoundary>
            </TabsContent>

            {/* ── Knowledge & Document Library Tab ── */}
            <TabsContent value="library" className="mt-4 space-y-6">
              {/* Workspace-scoped learning resources */}
              <SectionErrorBoundary label="Learning Resources">
                <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
                  <WorkspaceKnowledgePanel applicationId={appId} />
                </div>
              </SectionErrorBoundary>

              {/* Document library */}
              <SectionErrorBoundary label="Document Library">
                {docLibraryLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <DocumentLibraryView
                    documents={docLibrary}
                    onViewDocument={(doc) => {
                      // Navigate to the appropriate document tab if it's a core doc
                      const tabMap: Record<string, string> = {
                        cv: "cv", cover_letter: "cover", personal_statement: "statement", portfolio: "portfolio",
                      };
                      if (tabMap[doc.docType]) {
                        setTab(tabMap[doc.docType]);
                      }
                    }}
                    onGenerateDocument={async (doc) => {
                      try {
                        await generateDocumentInLibrary(doc.docType, doc.docCategory, appId, doc.label);
                        toast({ title: "Generation started", description: `Generating ${doc.label}…` });
                        // Immediate refresh — polling will continue while status is "generating"
                        fetchDocLibrary();
                      } catch {
                        toast({ title: "Generation failed", variant: "error" });
                      }
                    }}
                    onDownloadDocument={async (doc) => {
                      if (!doc.htmlContent) return;
                      await downloadPdf(doc.htmlContent, {
                        filename: doc.label.replace(/\s+/g, "_"),
                      });
                    }}
                  />
                )}
              </SectionErrorBoundary>
            </TabsContent>

            <TabsContent value="export" className="mt-4">
              <SectionErrorBoundary label="Export">
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
                        // Collect extra documents from benchmark + generated docs
                        const extras: Array<{ name: string; html: string; type?: string; category?: string }> = [];
                        // Benchmark documents
                        const benchDocs = app.benchmarkDocuments || {};
                        for (const [key, html] of Object.entries(benchDocs)) {
                          if (html) extras.push({ name: `Benchmark_${key.replace(/_/g, "_")}`, html: html as string, category: "benchmark" });
                        }
                        // Extra generated documents
                        const genDocs = app.generatedDocuments || {};
                        for (const [key, html] of Object.entries(genDocs)) {
                          if (html) extras.push({ name: key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()).replace(/\s+/g, "_"), html: html as string, category: "tailored" });
                        }
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
                          extraDocuments: extras,
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

                  {/* ── Dynamic Benchmark Document Cards ── */}
                  {Object.entries(app.benchmarkDocuments || {}).map(([key, html]) => {
                    if (!html) return null;
                    const label = `Benchmark ${key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())}`;
                    const fname = `HireStack_Benchmark_${key}`;
                    return (
                      <ExportCard
                        key={`bench-${key}`}
                        title={label}
                        description="Ideal-candidate benchmark version."
                        hasContent
                        gate={gatedDownload}
                        onDownloadPdf={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `bench_${key}_pdf` } });
                          await downloadPdf(html as string, { filename: fname, documentType: "cv" });
                        }}
                        onDownloadDocx={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `bench_${key}_docx` } });
                          await downloadDocx(html as string, { filename: fname, documentType: "cv" });
                        }}
                        onDownloadImage={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `bench_${key}_jpg` } });
                          await downloadImage(html as string, { filename: fname, documentType: "cv", format: "jpg" });
                        }}
                        onCopyText={() => navigator.clipboard.writeText(stripHtml(html as string))}
                      />
                    );
                  })}

                  {/* ── Dynamic Generated Document Cards ── */}
                  {Object.entries(app.generatedDocuments || {}).map(([key, html]) => {
                    if (!html) return null;
                    const label = key.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                    const fname = `HireStack_${key}`;
                    return (
                      <ExportCard
                        key={`gen-${key}`}
                        title={label}
                        description="AI-generated tailored document."
                        hasContent
                        gate={gatedDownload}
                        onDownloadPdf={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `gen_${key}_pdf` } });
                          await downloadPdf(html as string, { filename: fname, documentType: "cv" });
                        }}
                        onDownloadDocx={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `gen_${key}_docx` } });
                          await downloadDocx(html as string, { filename: fname, documentType: "cv" });
                        }}
                        onDownloadImage={async () => {
                          if (!user) return;
                          await trackEvent(user.uid, { name: "export_clicked", appId, properties: { type: `gen_${key}_jpg` } });
                          await downloadImage(html as string, { filename: fname, documentType: "cv", format: "jpg" });
                        }}
                        onCopyText={() => navigator.clipboard.writeText(stripHtml(html as string))}
                      />
                    );
                  })}
                </div>

                <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
                  <div className="text-xs font-semibold text-primary">Pro tip</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Use &ldquo;Download All (ZIP)&rdquo; to get every document as a branded PDF + Word bundle — ready to attach to any application. Snapshot your versions before exporting to keep a history.
                  </div>
                </div>
              </div>
              </SectionErrorBoundary>
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4 lg:sticky lg:top-6 h-fit">
          <SectionErrorBoundary label="Sidebar">
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
          <div ref={replayRef}>
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
          </div>

          <CoachPanel
            actions={coachActions}
            statusLine={`${taskStats.remaining} open tasks · ${evidence.length} evidence`}
            warning={(() => {
              const sc = app.scores ?? {};
              const dims = [
                { name: "Match", score: sc.match ?? 0 },
                { name: "ATS Readiness", score: sc.atsReadiness ?? 0 },
                { name: "6-Second Scan", score: sc.recruiterScan ?? 0 },
                { name: "Evidence Strength", score: sc.evidenceStrength ?? 0 },
              ].filter(d => d.score > 0);
              if (dims.length === 0) return undefined;
              const weakest = dims.sort((a, b) => a.score - b.score)[0];
              if (weakest.score >= 60) return undefined;
              return `${weakest.name} is at ${weakest.score}% — this is dragging down your overall readiness.`;
            })()}
            suggestion={(() => {
              const recs = app.gaps?.recommendations ?? [];
              if (recs.length > 0) return typeof recs[0] === "string" ? recs[0] : undefined;
              const topFix = app.scores?.topFix;
              return typeof topFix === "string" ? topFix : undefined;
            })()}
          />

          {/* Quick-action links to sidebar tools with application context */}
          <div className="rounded-2xl border bg-card p-4 shadow-soft-sm space-y-2">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Quick Tools</div>
            <Link href={`/interview?appId=${appId}`} className="flex items-center gap-2 rounded-xl border p-3 hover:bg-muted/50 transition-colors group">
              <MessageSquare className="h-4 w-4 text-blue-500" />
              <div className="min-w-0">
                <div className="text-sm font-medium group-hover:text-primary transition-colors">Practice Interview</div>
                <div className="text-2xs text-muted-foreground">Pre-filled with this role&apos;s context</div>
              </div>
            </Link>
            <Link href={`/salary?appId=${appId}`} className="flex items-center gap-2 rounded-xl border p-3 hover:bg-muted/50 transition-colors group">
              <DollarSign className="h-4 w-4 text-emerald-500" />
              <div className="min-w-0">
                <div className="text-sm font-medium group-hover:text-primary transition-colors">Salary Coach</div>
                <div className="text-2xs text-muted-foreground">Market data for this role</div>
              </div>
            </Link>
          </div>
          </SectionErrorBoundary>
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

      {/* Regeneration confirmation dialog */}
      <Dialog open={!!regenConfirm} onOpenChange={(o) => !o && setRegenConfirm(null)}>
        <DialogContent className="sm:max-w-sm rounded-2xl">
          <DialogHeader>
            <DialogTitle>Regenerate {regenConfirm?.label}?</DialogTitle>
            <DialogDescription>
              This will replace the current version with fresh AI content. Your previous version will be saved in{" "}
              <span className="font-medium text-foreground">Version History</span> so you can restore it if needed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" className="rounded-xl" onClick={() => setRegenConfirm(null)}>Cancel</Button>
            <Button className="rounded-xl gap-2" onClick={() => regenConfirm && doRegenerate(regenConfirm.module)}>
              <RefreshCw className="h-4 w-4" />
              Regenerate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
