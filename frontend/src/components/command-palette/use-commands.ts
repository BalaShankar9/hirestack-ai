"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

export interface Command {
  id: string;
  label: string;
  category: "recent" | "actions" | "navigate" | "tools";
  shortcut?: string;
  onSelect: () => void;
  icon?: string;
}

export function useCommands(): Command[] {
  const router = useRouter();

  return useMemo(
    () => [
      // Actions
      { id: "new-app", label: "New Application", category: "actions" as const, shortcut: "⌘N", onSelect: () => router.push("/new") },
      { id: "generate-cv", label: "Generate CV", category: "actions" as const, shortcut: "⌘G", onSelect: () => router.push("/new") },
      { id: "run-ats", label: "Run ATS Scan", category: "actions" as const, shortcut: "⌘S", onSelect: () => router.push("/ats-scanner") },
      { id: "start-interview", label: "Start Interview", category: "actions" as const, shortcut: "⌘I", onSelect: () => router.push("/interview") },
      { id: "export-all", label: "Export All", category: "actions" as const, shortcut: "⌘E", onSelect: () => router.push("/dashboard") },
      // Navigation — core pages (always in sidebar)
      { id: "nav-dashboard", label: "Overview", category: "navigate" as const, shortcut: "⌘1", onSelect: () => router.push("/dashboard") },
      { id: "nav-evidence", label: "Evidence", category: "navigate" as const, shortcut: "⌘2", onSelect: () => router.push("/evidence") },
      { id: "nav-profile", label: "Profile", category: "navigate" as const, shortcut: "⌘3", onSelect: () => router.push("/nexus") },
      { id: "nav-settings", label: "Settings", category: "navigate" as const, onSelect: () => router.push("/settings") },
      // Tools — secondary pages accessible via ⌘K
      { id: "nav-ats", label: "ATS Scanner", category: "tools" as const, onSelect: () => router.push("/ats-scanner") },
      { id: "nav-interview", label: "Interview Prep", category: "tools" as const, onSelect: () => router.push("/interview") },
      { id: "nav-salary", label: "Salary Coach", category: "tools" as const, onSelect: () => router.push("/salary") },
      { id: "nav-career", label: "Career Improvement", category: "tools" as const, onSelect: () => router.push("/career") },
      { id: "nav-analytics", label: "Career Analytics", category: "tools" as const, onSelect: () => router.push("/career-analytics") },
      { id: "nav-jobs", label: "Job Board", category: "tools" as const, onSelect: () => router.push("/job-board") },
      { id: "nav-learning", label: "Daily Learn", category: "tools" as const, onSelect: () => router.push("/learning") },
      { id: "nav-ab-lab", label: "Compare Versions", category: "tools" as const, onSelect: () => router.push("/ab-lab") },
      { id: "nav-api-keys", label: "API Keys", category: "tools" as const, onSelect: () => router.push("/api-keys") },
    ],
    [router]
  );
}
