"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "@/lib/api";
import type {
  KnowledgeResource,
  UserKnowledgeProgress,
} from "@/lib/firestore/models";
import { ResourceViewer } from "@/components/knowledge/resource-viewer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  Clock,
  ExternalLink,
  CheckCircle,
  Bookmark,
  Play,
  Loader2,
  Sparkles,
  Target,
  GraduationCap,
  ArrowRight,
  Star,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

/* ── Constants ────────────────────────────────────────────────────── */

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

/* ── Resource Mini Card ──────────────────────────────────────────── */

function ResourceMiniCard({
  resource,
  progress,
  onSave,
  onStart,
  onComplete,
  onClick,
}: {
  resource: KnowledgeResource;
  progress?: UserKnowledgeProgress;
  onSave: () => void;
  onStart: () => void;
  onComplete: () => void;
  onClick: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="group rounded-lg border bg-card p-3 hover:shadow-soft-sm transition-all cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className="h-8 w-8 shrink-0 rounded-md bg-primary/10 flex items-center justify-center mt-0.5">
          <BookOpen className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
            <Badge variant="secondary" className={cn("text-[9px] px-1.5 py-0", CATEGORY_COLORS[resource.category])}>
              {resource.category.replace(/_/g, " ")}
            </Badge>
            <Badge variant="outline" className={cn("text-[9px] px-1.5 py-0", DIFFICULTY_COLORS[resource.difficulty])}>
              {resource.difficulty}
            </Badge>
            {resource.is_featured && (
              <Star className="h-3 w-3 text-amber-500" />
            )}
          </div>
          <h4 className="text-xs font-medium leading-snug line-clamp-1">{resource.title}</h4>
          <p className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5">{resource.description}</p>

          <div className="flex items-center gap-1.5 mt-1.5" onClick={(e) => e.stopPropagation()}>
            {resource.content_html && (
              <Button size="sm" variant="outline" className="text-[10px] h-5 px-2" onClick={onClick}>
                <BookOpen className="h-2.5 w-2.5 mr-0.5" /> Read
              </Button>
            )}
            {resource.url && (
              <Button size="sm" variant="outline" className="text-[10px] h-5 px-2" asChild>
                <a href={resource.url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-2.5 w-2.5 mr-0.5" /> Open
                </a>
              </Button>
            )}
            {!progress ? (
              <Button size="sm" variant="ghost" className="text-[10px] h-5 px-2" onClick={onSave}>
                <Bookmark className="h-2.5 w-2.5 mr-0.5" /> Save
              </Button>
            ) : progress.status === "saved" ? (
              <Button size="sm" variant="ghost" className="text-[10px] h-5 px-2" onClick={onStart}>
                <Play className="h-2.5 w-2.5 mr-0.5" /> Start
              </Button>
            ) : progress.status === "in_progress" ? (
              <Button size="sm" variant="ghost" className="text-[10px] h-5 px-2" onClick={onComplete}>
                <CheckCircle className="h-2.5 w-2.5 mr-0.5" /> Done
              </Button>
            ) : (
              <span className="text-[10px] text-green-600 flex items-center gap-0.5">
                <CheckCircle className="h-2.5 w-2.5" /> Completed
              </span>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ── Workspace Knowledge Panel ───────────────────────────────────── */

interface WorkspaceKnowledgePanelProps {
  /** Application ID for workspace scoping */
  applicationId: string;
}

export function WorkspaceKnowledgePanel({ applicationId }: WorkspaceKnowledgePanelProps) {
  const [resources, setResources] = useState<KnowledgeResource[]>([]);
  const [progressMap, setProgressMap] = useState<Record<string, UserKnowledgeProgress>>({});
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [recsLoading, setRecsLoading] = useState(false);
  const [viewingResource, setViewingResource] = useState<KnowledgeResource | null>(null);
  const [showAll, setShowAll] = useState(false);

  const loadResources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.knowledge.listResources({ limit: 50 });
      setResources(Array.isArray(data) ? data : []);
    } catch {} finally {
      setLoading(false);
    }
  }, []);

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

  useEffect(() => {
    loadResources();
    loadProgress();
    loadRecommendations();
  }, [loadResources, loadProgress, loadRecommendations]);

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
      toast({ title: "Failed to update", variant: "error" });
    }
  };

  const handleGenerateRecs = async () => {
    setRecsLoading(true);
    try {
      const data = await api.knowledge.generateRecommendations();
      setRecommendations(Array.isArray(data) ? data : []);
      toast({ title: data?.length ? "Recommendations updated!" : "No skill gaps found" });
    } catch {
      toast({ title: "Failed to generate", variant: "error" });
    } finally {
      setRecsLoading(false);
    }
  };

  /* Build the recommended resources list */
  const recResources: KnowledgeResource[] = recommendations
    .map((r) => r.knowledge_resources)
    .filter(Boolean);

  /* Show recommended resources first, then featured, then the rest */
  const displayResources = showAll
    ? resources
    : recResources.length > 0
      ? recResources.slice(0, 6)
      : resources.filter((r) => r.is_featured).slice(0, 6);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GraduationCap className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">Learning Resources</h3>
          <span className="text-[10px] text-muted-foreground">
            {recResources.length > 0
              ? `${recResources.length} recommended for this role`
              : `${resources.length} available`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {recResources.length === 0 && (
            <Button
              size="sm"
              variant="outline"
              className="text-[10px] h-6 gap-1"
              onClick={handleGenerateRecs}
              disabled={recsLoading}
            >
              {recsLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
              Get Recommendations
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-[10px] h-6"
            onClick={() => setShowAll(!showAll)}
          >
            {showAll ? "Show Recommended" : "Browse All"} <ArrowRight className="h-3 w-3 ml-0.5" />
          </Button>
        </div>
      </div>

      {/* Recommended reason banner */}
      {recResources.length > 0 && !showAll && (
        <div className="rounded-lg bg-primary/5 border border-primary/10 px-3 py-2 flex items-center gap-2">
          <Target className="h-3.5 w-3.5 text-primary shrink-0" />
          <p className="text-[10px] text-primary/70">
            These resources are matched to your skill gaps for this application
          </p>
        </div>
      )}

      {/* Resource grid */}
      {displayResources.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {displayResources.map((r) => (
            <ResourceMiniCard
              key={r.id}
              resource={r}
              progress={progressMap[r.id]}
              onSave={() => handleProgress(r.id, "saved")}
              onStart={() => handleProgress(r.id, "in_progress")}
              onComplete={() => handleProgress(r.id, "completed")}
              onClick={() => setViewingResource(r)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-muted-foreground">
          <BookOpen className="h-6 w-6 mx-auto mb-2 opacity-30" />
          <p className="text-xs">No resources available</p>
        </div>
      )}

      {/* View more link */}
      {!showAll && displayResources.length < resources.length && (
        <div className="text-center">
          <Button
            size="sm"
            variant="ghost"
            className="text-xs h-7"
            onClick={() => setShowAll(true)}
          >
            View all {resources.length} resources <ArrowRight className="h-3 w-3 ml-1" />
          </Button>
        </div>
      )}

      {/* Resource viewer slide-over */}
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
    </div>
  );
}
