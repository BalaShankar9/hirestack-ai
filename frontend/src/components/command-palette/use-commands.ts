"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

export interface Command {
  id: string;
  label: string;
  category: "recent" | "actions" | "navigate";
  shortcut?: string;
  onSelect: () => void;
  icon?: string;
}

export function useCommands(): Command[] {
  const router = useRouter();

  return useMemo(
    () => [
      { id: "new-app", label: "New Application", category: "actions" as const, shortcut: "⌘N", onSelect: () => router.push("/new") },
      { id: "nav-dashboard", label: "Dashboard", category: "navigate" as const, shortcut: "⌘1", onSelect: () => router.push("/dashboard") },
      { id: "nav-evidence", label: "Evidence Vault", category: "navigate" as const, shortcut: "⌘2", onSelect: () => router.push("/evidence") },
      { id: "nav-analytics", label: "Career Analytics", category: "navigate" as const, shortcut: "⌘3", onSelect: () => router.push("/career-analytics") },
      { id: "nav-ats", label: "ATS Scanner", category: "navigate" as const, onSelect: () => router.push("/ats-scanner") },
      { id: "nav-interview", label: "Interview Prep", category: "navigate" as const, onSelect: () => router.push("/interview") },
      { id: "nav-salary", label: "Salary Coach", category: "navigate" as const, onSelect: () => router.push("/salary") },
      { id: "nav-jobs", label: "Job Board", category: "navigate" as const, onSelect: () => router.push("/job-board") },
      { id: "nav-learning", label: "Daily Learn", category: "navigate" as const, onSelect: () => router.push("/learning") },
      { id: "nav-ab-lab", label: "A/B Doc Lab", category: "navigate" as const, onSelect: () => router.push("/ab-lab") },
      { id: "nav-api-keys", label: "API Keys", category: "navigate" as const, onSelect: () => router.push("/api-keys") },
    ],
    [router]
  );
}
