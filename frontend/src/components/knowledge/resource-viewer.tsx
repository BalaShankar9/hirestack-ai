"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  ExternalLink,
  Clock,
  BookOpen,
  CheckCircle,
  Play,
  Bookmark,
  Star,
  ArrowLeft,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { KnowledgeResource, UserKnowledgeProgress } from "@/lib/firestore/models";

const CATEGORY_COLORS: Record<string, string> = {
  resume_writing: "bg-blue-500/10 text-blue-600",
  interview_prep: "bg-purple-500/10 text-purple-600",
  salary_negotiation: "bg-emerald-500/10 text-emerald-600",
  career_strategy: "bg-amber-500/10 text-amber-600",
  career_development: "bg-amber-500/10 text-amber-600",
  skill_development: "bg-indigo-500/10 text-indigo-600",
  networking: "bg-pink-500/10 text-pink-600",
  industry_knowledge: "bg-cyan-500/10 text-cyan-600",
  soft_skills: "bg-violet-500/10 text-violet-600",
  technical_skills: "bg-orange-500/10 text-orange-600",
  job_search: "bg-teal-500/10 text-teal-600",
  personal_branding: "bg-rose-500/10 text-rose-600",
  general: "bg-gray-500/10 text-gray-600",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: "bg-green-500/10 text-green-700",
  intermediate: "bg-yellow-500/10 text-yellow-700",
  advanced: "bg-red-500/10 text-red-700",
};

interface ResourceViewerProps {
  resource: KnowledgeResource;
  progress?: UserKnowledgeProgress;
  onClose: () => void;
  onSave: () => void;
  onStart: () => void;
  onComplete: () => void;
}

export function ResourceViewer({
  resource,
  progress,
  onClose,
  onSave,
  onStart,
  onComplete,
}: ResourceViewerProps) {
  // Lock body scroll while viewer is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex"
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose} />

        {/* Panel */}
        <motion.div
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 30, stiffness: 300 }}
          className="relative ml-auto h-full w-full max-w-2xl overflow-y-auto bg-background border-l shadow-2xl"
        >
          {/* Header */}
          <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm border-b px-6 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <Badge variant="secondary" className={cn("text-2xs", CATEGORY_COLORS[resource.category])}>
                    {resource.category.replace(/_/g, " ")}
                  </Badge>
                  <Badge variant="outline" className={cn("text-2xs", DIFFICULTY_COLORS[resource.difficulty])}>
                    {resource.difficulty}
                  </Badge>
                  {resource.is_featured && (
                    <Badge className="text-2xs bg-amber-500/10 text-amber-600 border-0">
                      <Star className="h-3 w-3 mr-0.5" /> Featured
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-2xs">{resource.resource_type}</Badge>
                </div>
                <h2 className="text-lg font-bold leading-tight">{resource.title}</h2>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                  {resource.provider && <span>{resource.provider}</span>}
                  {resource.estimated_time && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" /> {resource.estimated_time}
                    </span>
                  )}
                </div>
              </div>
              <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Action bar */}
            <div className="flex items-center gap-2 mt-3">
              {resource.url && (
                <Button size="sm" variant="outline" className="text-xs h-8 gap-1.5" asChild>
                  <a href={resource.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-3.5 w-3.5" /> Open Original
                  </a>
                </Button>
              )}
              {!progress ? (
                <Button size="sm" variant="default" className="text-xs h-8 gap-1.5" onClick={onSave}>
                  <Bookmark className="h-3.5 w-3.5" /> Save to Library
                </Button>
              ) : progress.status === "saved" ? (
                <Button size="sm" variant="default" className="text-xs h-8 gap-1.5" onClick={onStart}>
                  <Play className="h-3.5 w-3.5" /> Start Learning
                </Button>
              ) : progress.status === "in_progress" ? (
                <Button size="sm" variant="default" className="text-xs h-8 gap-1.5" onClick={onComplete}>
                  <CheckCircle className="h-3.5 w-3.5" /> Mark Complete
                </Button>
              ) : (
                <Badge className="text-xs bg-green-500/10 text-green-600 border-0 gap-1">
                  <CheckCircle className="h-3.5 w-3.5" /> Completed
                </Badge>
              )}
            </div>
          </div>

          {/* Skills & tags */}
          {(resource.skills?.length > 0 || resource.tags?.length) && (
            <div className="px-6 py-3 border-b">
              <div className="flex flex-wrap gap-1.5">
                {resource.skills?.map((s) => (
                  <Badge key={s} variant="secondary" className="text-2xs">{s.replace(/_/g, " ")}</Badge>
                ))}
                {resource.tags?.map((t) => (
                  <Badge key={t} variant="outline" className="text-2xs font-normal">{t.replace(/_/g, " ")}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Content body */}
          <div className="px-6 py-6">
            {resource.content_html ? (
              <article
                className="prose prose-sm max-w-none dark:prose-invert prose-headings:font-semibold prose-headings:text-foreground prose-p:text-muted-foreground prose-a:text-primary prose-a:underline-offset-2 prose-li:text-muted-foreground"
                dangerouslySetInnerHTML={{ __html: resource.content_html }}
              />
            ) : resource.description ? (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground leading-relaxed">{resource.description}</p>
                {resource.url && (
                  <div className="rounded-xl border border-primary/20 bg-primary/5 p-5 text-center">
                    <BookOpen className="h-8 w-8 mx-auto mb-2 text-primary/60" />
                    <p className="text-sm font-medium mb-1">Full content available externally</p>
                    <p className="text-xs text-muted-foreground mb-3">
                      Open the original resource to access the complete material.
                    </p>
                    <Button size="sm" asChild>
                      <a href={resource.url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Open Resource
                      </a>
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No content available for this resource yet.</p>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
