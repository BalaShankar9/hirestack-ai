"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type {
  KnowledgeResource,
  UserKnowledgeProgress,
  ResourceRecommendation,
  ResourceCategory,
  ResourceType,
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
  Filter,
  Sparkles,
  X,
  ChevronDown,
  FileText,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

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
  onSave,
  onStart,
  onComplete,
}: {
  resource: KnowledgeResource;
  progress?: UserKnowledgeProgress;
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
      className="group rounded-xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
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

      <div className="flex items-center gap-2 pt-2 border-t">
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

/* ── Main Page ─────────────────────────────────────────────────────── */

export default function KnowledgeLibraryPage() {
  const { session } = useAuth();
  const [resources, setResources] = useState<KnowledgeResource[]>([]);
  const [progressMap, setProgressMap] = useState<Record<string, UserKnowledgeProgress>>({});
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [userDocs, setUserDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [tab, setTab] = useState<"browse" | "saved" | "recommended" | "documents">("browse");

  useEffect(() => {
    if (session?.access_token) api.setToken(session.access_token);
  }, [session?.access_token]);

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

  const filteredForTab = tab === "saved"
    ? resources.filter((r) => progressMap[r.id])
    : tab === "recommended"
    ? resources.filter((r) => recommendations.some((rec: any) => rec.resource_id === r.id))
    : resources;

  return (
    <div className="container max-w-6xl py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Library className="h-6 w-6 text-primary" /> Knowledge Library
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Free guides, templates, books, and resources to level up your career
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b pb-0">
        {(["browse", "saved", "recommended", "documents"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "browse" ? "Browse" : t === "saved" ? "My Library" : t === "recommended" ? "Recommended" : "My Documents"}
            {t === "recommended" && recommendations.length > 0 && (
              <Badge className="ml-1.5 text-2xs" variant="secondary">{recommendations.length}</Badge>
            )}
            {t === "documents" && userDocs.length > 0 && (
              <Badge className="ml-1.5 text-2xs" variant="secondary">{userDocs.length}</Badge>
            )}
          </button>
        ))}
      </div>

      {/* Filters (browse tab) */}
      {tab === "browse" && (
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
      )}

      {/* Recommended banner */}
      {tab === "browse" && recommendations.length > 0 && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm font-medium">Personalized for you</p>
              <p className="text-xs text-muted-foreground">{recommendations.length} resources matched to your skill gaps</p>
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setTab("recommended")}>
            View All
          </Button>
        </div>
      )}

      {/* Resource grid */}
      {tab === "documents" ? (
        /* ── My Documents tab ─────────────────────────────────────── */
        userDocs.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <FileText className="h-10 w-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No documents yet — create an application to generate documents</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {userDocs.map((doc: any) => (
              <motion.div
                key={doc.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="group rounded-xl border bg-card p-5 shadow-soft-sm hover:shadow-soft-md transition-all duration-200"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Badge variant="secondary" className={cn("text-2xs",
                        doc.doc_category === "tailored" ? "bg-violet-500/10 text-violet-600" :
                        doc.doc_category === "benchmark" ? "bg-amber-500/10 text-amber-600" :
                        "bg-blue-500/10 text-blue-600"
                      )}>
                        {doc.doc_category}
                      </Badge>
                      <Badge variant="outline" className={cn("text-2xs",
                        doc.status === "ready" ? "text-green-600" :
                        doc.status === "generating" ? "text-blue-600" :
                        doc.status === "error" ? "text-red-600" : "text-muted-foreground"
                      )}>
                        {doc.status}
                      </Badge>
                    </div>
                    <h3 className="font-semibold text-sm leading-snug line-clamp-2">
                      {doc.label || doc.doc_type?.replace(/_/g, " ")}
                    </h3>
                  </div>
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  {doc.doc_type?.replace(/_/g, " ")}
                  {doc.version && doc.version > 1 ? ` · v${doc.version}` : ""}
                </p>
                {doc.updated_at && (
                  <p className="text-2xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {new Date(doc.updated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                  </p>
                )}
              </motion.div>
            ))}
          </div>
        )
      ) : loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filteredForTab.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <BookOpen className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {tab === "saved" ? "No saved resources yet" : tab === "recommended" ? "No recommendations yet — sync your skill gaps first" : "No resources found"}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredForTab.map((r) => (
            <ResourceCard
              key={r.id}
              resource={r}
              progress={progressMap[r.id]}
              onSave={() => handleProgress(r.id, "saved")}
              onStart={() => handleProgress(r.id, "in_progress")}
              onComplete={() => handleProgress(r.id, "completed")}
            />
          ))}
        </div>
      )}
    </div>
  );
}
