"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type {
  KnowledgeResource,
  UserKnowledgeProgress,
  ResourceCategory,
  ResourceDifficulty,
} from "@/lib/firestore/models";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  Library,
  Search,
  Star,
  BookOpen,
  Clock,
  ExternalLink,
  CheckCircle,
  Bookmark,
  Play,
  Loader2,
  Sparkles,
  X,
  FileText,
  RefreshCw,
  Lightbulb,
  FolderOpen,
  TrendingUp,
  BarChart3,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { ResourceViewer } from "@/components/knowledge/resource-viewer";
import { DOCUMENT_UNIVERSE } from "@/lib/document-universe";
import { DocumentUniverseGrid, type DocStatus } from "@/components/workspace/document-universe-grid";

/* ── Types ─────────────────────────────────────────────────────────── */
type TabKey = "learn" | "library" | "recommended" | "documents";

/* ── Constants ─────────────────────────────────────────────────────── */

const CATEGORIES: { value: ResourceCategory | ""; label: string }[] = [
  { value: "", label: "All Categories" },
  { value: "resume_writing", label: "Resume Writing" },
  { value: "interview_prep", label: "Interview Prep" },
  { value: "salary_negotiation", label: "Salary Negotiation" },
  { value: "career_strategy", label: "Career Strategy" },
  { value: "career_development", label: "Career Development" },
  { value: "skill_development", label: "Skill Development" },
  { value: "networking", label: "Networking" },
  { value: "industry_knowledge", label: "Industry Knowledge" },
  { value: "soft_skills", label: "Soft Skills" },
  { value: "technical_skills", label: "Technical Skills" },
  { value: "job_search", label: "Job Search" },
  { value: "personal_branding", label: "Personal Branding" },
  { value: "general", label: "General" },
];

const DIFFICULTIES: { value: ResourceDifficulty | ""; label: string }[] = [
  { value: "", label: "All Levels" },
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

const CATEGORY_COLORS: Record<string, string> = {
  resume_writing: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  interview_prep: "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  salary_negotiation: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  career_strategy: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  career_development: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  skill_development: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  networking: "bg-pink-500/10 text-pink-600 dark:text-pink-400",
  industry_knowledge: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  soft_skills: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  technical_skills: "bg-orange-500/10 text-orange-600 dark:text-orange-400",
  job_search: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  personal_branding: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  general: "bg-gray-500/10 text-gray-600 dark:text-gray-400",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: "bg-green-500/10 text-green-700 dark:text-green-400",
  intermediate: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400",
  advanced: "bg-red-500/10 text-red-700 dark:text-red-400",
};

/* ── Resource Card ─────────────────────────────────────────────────── */

function ResourceCard({
  resource,
  progress,
  onClick,
  onSave,
  onStart,
  onComplete,
}: {
  resource: KnowledgeResource;
  progress?: UserKnowledgeProgress;
  onClick: () => void;
  onSave: () => void;
  onStart: () => void;
  onComplete: () => void;
}) {
  const statusIcon = progress?.status === "completed" ? (
    <CheckCircle className="h-4 w-4 text-green-500" />
  ) : progress?.status === "in_progress" ? (
    <Play className="h-4 w-4 text-blue-500" />
  ) : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="group rounded-xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md transition-all duration-200 cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <Badge variant="secondary" className={cn("text-2xs", CATEGORY_COLORS[resource.category])}>
              {resource.category.replace(/_/g, " ")}
            </Badge>
            <Badge variant="outline" className={cn("text-2xs", DIFFICULTY_COLORS[resource.difficulty])}>
              {resource.difficulty}
            </Badge>
            {resource.is_featured && (
              <Badge className="text-2xs bg-amber-500/10 text-amber-600">
                <Star className="h-3 w-3 mr-0.5" /> Featured
              </Badge>
            )}
          </div>
          <h3 className="font-semibold text-sm leading-snug line-clamp-2">{resource.title}</h3>
        </div>
        {statusIcon && <div className="shrink-0">{statusIcon}</div>}
      </div>

      <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{resource.description}</p>

      <div className="flex items-center gap-3 text-2xs text-muted-foreground mb-3">
        {resource.provider && <span>{resource.provider}</span>}
        {resource.estimated_time && (
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" /> {resource.estimated_time}
          </span>
        )}
        <Badge variant="outline" className="text-2xs">{resource.resource_type}</Badge>
      </div>

      {resource.skills?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {resource.skills.slice(0, 4).map((s) => (
            <Badge key={s} variant="outline" className="text-2xs font-normal">{s}</Badge>
          ))}
          {resource.skills.length > 4 && (
            <Badge variant="outline" className="text-2xs font-normal">+{resource.skills.length - 4}</Badge>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 border-t" onClick={(e) => e.stopPropagation()}>
        {resource.url && (
          <Button size="sm" variant="outline" className="text-xs h-7" asChild>
            <a href={resource.url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3 w-3 mr-1" /> Open
            </a>
          </Button>
        )}
        {!progress ? (
          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={onSave}>
            <Bookmark className="h-3 w-3 mr-1" /> Save
          </Button>
        ) : progress.status === "saved" ? (
          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={onStart}>
            <Play className="h-3 w-3 mr-1" /> Start
          </Button>
        ) : progress.status === "in_progress" ? (
          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={onComplete}>
            <CheckCircle className="h-3 w-3 mr-1" /> Complete
          </Button>
        ) : null}
      </div>
    </motion.div>
  );
}

/* ── Recommendation Card ───────────────────────────────────────────── */

function RecommendationCard({
  rec,
  onOpen,
  onDismiss,
}: {
  rec: any;
  onOpen: () => void;
  onDismiss: () => void;
}) {
  const resource = rec.knowledge_resources || rec;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md transition-all duration-200 cursor-pointer"
      onClick={onOpen}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="font-semibold text-sm leading-snug line-clamp-2 flex-1">
          {resource.title || "Recommended Resource"}
        </h3>
        <Button size="sm" variant="ghost" className="h-6 w-6 p-0 shrink-0" onClick={(e) => { e.stopPropagation(); onDismiss(); }}>
          <X className="h-3 w-3" />
        </Button>
      </div>
      {resource.description && (
        <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{resource.description}</p>
      )}
      {rec.reason && (
        <div className="rounded-lg bg-primary/5 border border-primary/10 p-3 mb-3">
          <div className="flex items-start gap-2">
            <Lightbulb className="h-3.5 w-3.5 text-primary shrink-0 mt-0.5" />
            <p className="text-xs text-primary/80 leading-relaxed">{rec.reason}</p>
          </div>
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        {resource.category && (
          <Badge variant="secondary" className={cn("text-2xs", CATEGORY_COLORS[resource.category])}>
            {resource.category.replace(/_/g, " ")}
          </Badge>
        )}
        {resource.difficulty && (
          <Badge variant="outline" className={cn("text-2xs", DIFFICULTY_COLORS[resource.difficulty])}>
            {resource.difficulty}
          </Badge>
        )}
        {resource.estimated_time && (
          <span className="text-2xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" /> {resource.estimated_time}
          </span>
        )}
      </div>
    </motion.div>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export default function KnowledgeLibraryPage() {
  const { session } = useAuth();
  const [resources, setResources] = useState<KnowledgeResource[]>([]);
  const [progressMap, setProgressMap] = useState<Record<string, UserKnowledgeProgress>>({});
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [userDocs, setUserDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [recsLoading, setRecsLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [tab, setTab] = useState<TabKey>("learn");
  const [viewingResource, setViewingResource] = useState<KnowledgeResource | null>(null);

  useEffect(() => {
    if (session?.access_token) api.setToken(session.access_token);
  }, [session?.access_token]);

  /* ── Data loaders ──────────────────────────────────────────────── */

  const loadResources = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { limit: 50 };
      if (category) params.category = category;
      if (difficulty) params.difficulty = difficulty;
      if (search) params.search = search;
      const data = await api.knowledge.listResources(params);
      setResources(Array.isArray(data) ? data : []);
    } catch {
      toast({ title: "Failed to load resources", variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [category, difficulty, search]);

  const loadProgress = useCallback(async () => {
    try {
      const data = await api.knowledge.getProgress();
      const map: Record<string, UserKnowledgeProgress> = {};
      (Array.isArray(data) ? data : []).forEach((p: UserKnowledgeProgress) => {
        map[p.resource_id] = p;
      });
      setProgressMap(map);
    } catch {}
  }, []);

  const loadRecommendations = useCallback(async () => {
    try {
      const data = await api.knowledge.getRecommendations();
      setRecommendations(Array.isArray(data) ? data : []);
    } catch {}
  }, []);

  const loadDocuments = useCallback(async () => {
    try {
      const resp = await api.knowledge.getAllDocuments({ limit: 200 });
      setUserDocs(Array.isArray(resp?.documents) ? resp.documents : []);
    } catch {}
  }, []);

  useEffect(() => { loadResources(); }, [loadResources]);
  useEffect(() => { loadProgress(); loadRecommendations(); loadDocuments(); }, [loadProgress, loadRecommendations, loadDocuments]);

  // Auto-generate recommendations if none exist on first load
  useEffect(() => {
    if (loading || recsLoading) return;
    if (recommendations.length === 0 && resources.length > 0) {
      handleGenerateRecs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  /* ── Actions ───────────────────────────────────────────────────── */

  const handleProgress = async (resourceId: string, status: "saved" | "in_progress" | "completed") => {
    try {
      await api.knowledge.saveProgress({
        resource_id: resourceId,
        status,
        progress_pct: status === "completed" ? 100 : status === "in_progress" ? 50 : 0,
      });
      await loadProgress();
      toast({ title: status === "saved" ? "Saved!" : status === "completed" ? "Completed!" : "Started!" });
    } catch {
      toast({ title: "Failed to update progress", variant: "error" });
    }
  };

  const handleGenerateRecs = async () => {
    setRecsLoading(true);
    try {
      await api.knowledge.generateRecommendations();
      await loadRecommendations();
      toast({ title: "Recommendations updated" });
    } catch {
      toast({ title: "Failed to generate recommendations", variant: "error" });
    } finally {
      setRecsLoading(false);
    }
  };

  const handleDismissRec = async (recId: string) => {
    try {
      await api.knowledge.dismissRecommendation(recId);
      setRecommendations((prev) => prev.filter((r) => r.id !== recId));
    } catch {}
  };

  /* ── Derived data ──────────────────────────────────────────────── */

  const savedResources = useMemo(
    () => resources.filter((r) => progressMap[r.id]?.status === "saved"),
    [resources, progressMap]
  );
  const inProgressResources = useMemo(
    () => resources.filter((r) => progressMap[r.id]?.status === "in_progress"),
    [resources, progressMap]
  );
  const completedResources = useMemo(
    () => resources.filter((r) => progressMap[r.id]?.status === "completed"),
    [resources, progressMap]
  );

  const docStatusMap = useMemo(() => {
    const map = new Map<string, DocStatus>();
    for (const doc of userDocs) {
      if (doc.doc_type) {
        map.set(doc.doc_type, {
          status: doc.status || "planned",
          version: doc.version,
          updatedAt: doc.updated_at ? new Date(doc.updated_at).getTime() : undefined,
          label: doc.label,
        });
      }
    }
    return map;
  }, [userDocs]);

  const groupedDocs = useMemo(() => {
    const groups: Record<string, any[]> = {};
    for (const doc of userDocs) {
      const key = doc.doc_type || "other";
      if (!groups[key]) groups[key] = [];
      groups[key].push(doc);
    }
    return groups;
  }, [userDocs]);

  /* ── Helpers ───────────────────────────────────────────────────── */

  const openResource = (r: KnowledgeResource) => setViewingResource(r);

  const findResourceForRec = (rec: any): KnowledgeResource | null => {
    const nested = rec.knowledge_resources;
    if (nested) return nested as KnowledgeResource;
    return resources.find((r) => r.id === rec.resource_id) || null;
  };

  return (
    <div className="container max-w-6xl py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Library className="h-6 w-6 text-primary" /> Knowledge Library
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Guides, resources, and documents to level up your career
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b pb-0 overflow-x-auto -mx-1 px-1">
        {([
          { key: "learn" as TabKey, label: "Learn", icon: BookOpen },
          { key: "library" as TabKey, label: "My Library", icon: FolderOpen },
          { key: "recommended" as TabKey, label: "Recommended", icon: Sparkles },
          { key: "documents" as TabKey, label: "My Documents", icon: FileText },
        ]).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "shrink-0 whitespace-nowrap px-3 sm:px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5",
              tab === key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
            {key === "recommended" && recommendations.length > 0 && (
              <Badge className="ml-1 text-2xs h-4 min-w-[16px] px-1" variant="secondary">{recommendations.length}</Badge>
            )}
            {key === "library" && Object.keys(progressMap).length > 0 && (
              <Badge className="ml-1 text-2xs h-4 min-w-[16px] px-1" variant="secondary">{Object.keys(progressMap).length}</Badge>
            )}
          </button>
        ))}
      </div>

      {/* ── Learn Tab ─────────────────────────────────────────────── */}
      {tab === "learn" && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search resources..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 h-9 text-sm"
              />
            </div>
            <select
              title="Filter by category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-9 rounded-md border bg-background px-3 text-sm"
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <select
              title="Filter by difficulty"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
              className="h-9 rounded-md border bg-background px-3 text-sm"
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
            {(category || difficulty || search) && (
              <Button size="sm" variant="ghost" className="h-9 text-xs" onClick={() => { setCategory(""); setDifficulty(""); setSearch(""); }}>
                <X className="h-3 w-3 mr-1" /> Clear
              </Button>
            )}
          </div>

          {/* Recommended banner */}
          {recommendations.length > 0 && (
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Sparkles className="h-5 w-5 text-primary" />
                <div>
                  <p className="text-sm font-medium">Personalized for you</p>
                  <p className="text-xs text-muted-foreground">{recommendations.length} resources matched to your skill gaps</p>
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={() => setTab("recommended")}>View All</Button>
            </div>
          )}

          {/* Resource grid */}
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : resources.length === 0 ? (
            <div className="text-center py-20 text-muted-foreground">
              <BookOpen className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No resources found</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {resources.map((r) => (
                <ResourceCard
                  key={r.id}
                  resource={r}
                  progress={progressMap[r.id]}
                  onClick={() => openResource(r)}
                  onSave={() => handleProgress(r.id, "saved")}
                  onStart={() => handleProgress(r.id, "in_progress")}
                  onComplete={() => handleProgress(r.id, "completed")}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── My Library Tab ────────────────────────────────────────── */}
      {tab === "library" && (
        <>
          {/* Stats strip */}
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-xl border bg-card p-4 text-center">
              <div className="text-2xl font-bold text-blue-600">{inProgressResources.length}</div>
              <p className="text-xs text-muted-foreground mt-1">In Progress</p>
            </div>
            <div className="rounded-xl border bg-card p-4 text-center">
              <div className="text-2xl font-bold text-amber-600">{savedResources.length}</div>
              <p className="text-xs text-muted-foreground mt-1">Saved</p>
            </div>
            <div className="rounded-xl border bg-card p-4 text-center">
              <div className="text-2xl font-bold text-green-600">{completedResources.length}</div>
              <p className="text-xs text-muted-foreground mt-1">Completed</p>
            </div>
          </div>

          {Object.keys(progressMap).length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Bookmark className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium mb-1">Your library is empty</p>
              <p className="text-xs mb-4">Save or start resources from the Learn tab to see them here</p>
              <Button size="sm" variant="outline" onClick={() => setTab("learn")}>
                <BookOpen className="h-3.5 w-3.5 mr-1.5" /> Browse Resources
              </Button>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Continue Learning */}
              {inProgressResources.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <Play className="h-4 w-4 text-blue-500" /> Continue Learning
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {inProgressResources.map((r) => (
                      <ResourceCard key={r.id} resource={r} progress={progressMap[r.id]} onClick={() => openResource(r)} onSave={() => handleProgress(r.id, "saved")} onStart={() => handleProgress(r.id, "in_progress")} onComplete={() => handleProgress(r.id, "completed")} />
                    ))}
                  </div>
                </div>
              )}
              {/* Saved for Later */}
              {savedResources.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <Bookmark className="h-4 w-4 text-amber-500" /> Saved for Later
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {savedResources.map((r) => (
                      <ResourceCard key={r.id} resource={r} progress={progressMap[r.id]} onClick={() => openResource(r)} onSave={() => handleProgress(r.id, "saved")} onStart={() => handleProgress(r.id, "in_progress")} onComplete={() => handleProgress(r.id, "completed")} />
                    ))}
                  </div>
                </div>
              )}
              {/* Completed */}
              {completedResources.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500" /> Completed
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {completedResources.map((r) => (
                      <ResourceCard key={r.id} resource={r} progress={progressMap[r.id]} onClick={() => openResource(r)} onSave={() => handleProgress(r.id, "saved")} onStart={() => handleProgress(r.id, "in_progress")} onComplete={() => handleProgress(r.id, "completed")} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Recommended Tab ───────────────────────────────────────── */}
      {tab === "recommended" && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" /> Recommended for You
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">Resources matched to your skill gaps and career goals</p>
            </div>
            <Button size="sm" variant="outline" onClick={handleGenerateRecs} disabled={recsLoading}>
              {recsLoading ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
              {recommendations.length > 0 ? "Refresh" : "Generate"}
            </Button>
          </div>

          {recsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : recommendations.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <TrendingUp className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium mb-1">No recommendations yet</p>
              <p className="text-xs mb-4">Generate personalized recommendations based on your profile and skill gaps</p>
              <Button size="sm" onClick={handleGenerateRecs}>
                <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Generate Recommendations
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recommendations.map((rec) => (
                <RecommendationCard
                  key={rec.id}
                  rec={rec}
                  onOpen={() => {
                    const r = findResourceForRec(rec);
                    if (r) openResource(r);
                  }}
                  onDismiss={() => handleDismissRec(rec.id)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── My Documents Tab ──────────────────────────────────────── */}
      {tab === "documents" && (
        <>
          {/* Full Document Universe Grid */}
          <div>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" /> Document Universe
            </h2>
            <p className="text-xs text-muted-foreground mb-4">
              All {DOCUMENT_UNIVERSE.length} document types — generated docs show status overlays
            </p>
            <DocumentUniverseGrid universe={DOCUMENT_UNIVERSE} statusMap={docStatusMap} />
          </div>

          {/* Generated Documents History */}
          {userDocs.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" /> Generated Documents
              </h2>
              <div className="space-y-4">
                {Object.entries(groupedDocs).map(([docType, docs]) => (
                  <div key={docType} className="rounded-xl border bg-card p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-medium capitalize">{docType.replace(/_/g, " ")}</h3>
                      <Badge variant="secondary" className="text-2xs">{docs.length} version{docs.length > 1 ? "s" : ""}</Badge>
                    </div>
                    <div className="space-y-2">
                      {docs.map((doc: any) => (
                        <div key={doc.id} className="flex items-center justify-between text-xs border-t pt-2 first:border-0 first:pt-0">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={cn("text-2xs",
                              doc.status === "ready" ? "text-green-600 border-green-200" :
                              doc.status === "generating" ? "text-blue-600 border-blue-200" :
                              doc.status === "error" ? "text-red-600 border-red-200" : ""
                            )}>
                              {doc.status}
                            </Badge>
                            <Badge variant="secondary" className={cn("text-2xs",
                              doc.doc_category === "tailored" ? "bg-violet-500/10 text-violet-600" :
                              doc.doc_category === "benchmark" ? "bg-amber-500/10 text-amber-600" :
                              "bg-blue-500/10 text-blue-600"
                            )}>
                              {doc.doc_category}
                            </Badge>
                            {doc.version && doc.version > 1 && (
                              <span className="text-muted-foreground">v{doc.version}</span>
                            )}
                          </div>
                          {doc.updated_at && (
                            <span className="text-muted-foreground flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {new Date(doc.updated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" })}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {userDocs.length === 0 && (
            <div className="text-center py-12 text-muted-foreground border rounded-xl bg-card">
              <FileText className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium mb-1">No generated documents yet</p>
              <p className="text-xs">Create an application workspace to start generating documents</p>
            </div>
          )}
        </>
      )}

      {/* ── Resource Viewer Slide-over ────────────────────────────── */}
      <AnimatePresence>
        {viewingResource && (
          <ResourceViewer
            resource={viewingResource}
            progress={progressMap[viewingResource.id]}
            onClose={() => setViewingResource(null)}
            onSave={() => handleProgress(viewingResource.id, "saved")}
            onStart={() => handleProgress(viewingResource.id, "in_progress")}
            onComplete={() => handleProgress(viewingResource.id, "completed")}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
