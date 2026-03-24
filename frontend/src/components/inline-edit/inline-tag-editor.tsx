"use client";

import { memo, useCallback, useState } from "react";
import { X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface InlineTagEditorProps {
  tags: string[];
  onUpdate: (tags: string[]) => void;
  className?: string;
}

export const InlineTagEditor = memo(function InlineTagEditor({
  tags,
  onUpdate,
  className,
}: InlineTagEditorProps) {
  const [adding, setAdding] = useState(false);
  const [newTag, setNewTag] = useState("");

  const handleRemove = useCallback((idx: number) => {
    onUpdate(tags.filter((_, i) => i !== idx));
  }, [tags, onUpdate]);

  const handleAdd = useCallback(() => {
    const trimmed = newTag.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onUpdate([...tags, trimmed]);
    }
    setNewTag("");
    setAdding(false);
  }, [newTag, tags, onUpdate]);

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {tags.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-mono font-medium animate-bounce-sm"
        >
          {tag}
          <button
            onClick={() => handleRemove(i)}
            className="hover:text-destructive transition-colors"
            aria-label={`Remove ${tag}`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      {adding ? (
        <input
          autoFocus
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onBlur={handleAdd}
          onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); if (e.key === "Escape") setAdding(false); }}
          className="text-xs font-mono bg-transparent border-b border-primary/40 outline-none w-24"
          placeholder="Add tag..."
        />
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md border border-dashed border-muted-foreground/30 text-xs text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          aria-label="Add tag"
        >
          <Plus className="h-3 w-3" />
        </button>
      )}
    </div>
  );
});
