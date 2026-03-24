"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface InlineEditableProps {
  value: string;
  onSave: (newValue: string) => void;
  className?: string;
  inputClassName?: string;
  placeholder?: string;
}

export const InlineEditable = memo(function InlineEditable({
  value,
  onSave,
  className = "",
  inputClassName = "",
  placeholder = "Click to edit",
}: InlineEditableProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleSave = useCallback(() => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) {
      onSave(trimmed);
    } else {
      setDraft(value);
    }
    setEditing(false);
  }, [draft, value, onSave]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSave();
      if (e.key === "Escape") {
        setDraft(value);
        setEditing(false);
      }
    },
    [handleSave, value]
  );

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className={cn("bg-transparent border-b border-primary/40 outline-none text-sm", inputClassName)}
      />
    );
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={() => { setDraft(value); setEditing(true); }}
      onKeyDown={(e) => { if (e.key === "Enter") { setDraft(value); setEditing(true); } }}
      className={cn("cursor-pointer transition-colors hover:bg-primary/5 hover:rounded hover:px-1 hover:-mx-1", className)}
    >
      {value || <span className="text-muted-foreground italic">{placeholder}</span>}
    </span>
  );
});
