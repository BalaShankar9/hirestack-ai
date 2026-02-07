"use client";

import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";
import { Diff, FileEdit } from "lucide-react";

export function DiffToggle({
  mode,
  onChange,
}: {
  mode: "edit" | "diff";
  onChange: (mode: "edit" | "diff") => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-xl border bg-card p-1">
      <Toggle
        pressed={mode === "edit"}
        onPressedChange={() => onChange("edit")}
        className={cn("gap-2", mode === "edit" && "bg-muted")}
      >
        <FileEdit className="h-4 w-4" />
        Edit
      </Toggle>
      <Toggle
        pressed={mode === "diff"}
        onPressedChange={() => onChange("diff")}
        className={cn("gap-2", mode === "diff" && "bg-muted")}
      >
        <Diff className="h-4 w-4" />
        Diff
      </Toggle>
    </div>
  );
}

