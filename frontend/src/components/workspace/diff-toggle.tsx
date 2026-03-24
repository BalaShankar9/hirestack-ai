"use client";

import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";
import { Diff, FileEdit, Eye } from "lucide-react";

export type DocMode = "view" | "edit" | "diff";

export function ModeToggle({
  mode,
  onChange,
}: {
  mode: DocMode;
  onChange: (mode: DocMode) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-xl border bg-card p-1">
      <Toggle
        pressed={mode === "view"}
        onPressedChange={() => onChange("view")}
        className={cn("gap-2 h-8 px-3 text-xs", mode === "view" && "bg-muted")}
      >
        <Eye className="h-3.5 w-3.5" />
        View
      </Toggle>
      <Toggle
        pressed={mode === "edit"}
        onPressedChange={() => onChange("edit")}
        className={cn("gap-2 h-8 px-3 text-xs", mode === "edit" && "bg-muted")}
      >
        <FileEdit className="h-3.5 w-3.5" />
        Edit
      </Toggle>
      <Toggle
        pressed={mode === "diff"}
        onPressedChange={() => onChange("diff")}
        className={cn("gap-2 h-8 px-3 text-xs", mode === "diff" && "bg-muted")}
      >
        <Diff className="h-3.5 w-3.5" />
        Diff
      </Toggle>
    </div>
  );
}

// Backward-compatible export
export const DiffToggle = ModeToggle;
