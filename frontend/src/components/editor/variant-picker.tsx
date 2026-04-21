"use client";

import { useState } from "react";
import type { DocVariant } from "@/lib/firestore/models";

export interface VariantPickerProps {
  /** Human label rendered above the radios, e.g. "CV style" */
  title: string;
  variants: DocVariant[];
  /** Called when user picks a different variant; should perform the lock
   * RPC and return the updated html + variants so the caller can update
   * its local editor/snapshot state. */
  onLock: (variantKey: string) => Promise<void>;
  disabled?: boolean;
}

function _preview(content: string, max = 200): string {
  if (!content) return "";
  // Strip tags for preview line.
  const text = content.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return text.length > max ? text.slice(0, max - 1) + "\u2026" : text;
}

export function VariantPicker({ title, variants, onLock, disabled = false }: VariantPickerProps) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!variants || variants.length < 2) {
    // Nothing meaningful to pick between; hide.
    return null;
  }

  const handleSelect = async (key: string, currentlyLocked: boolean) => {
    if (currentlyLocked || busyKey || disabled) return;
    setError(null);
    setBusyKey(key);
    try {
      await onLock(key);
    } catch (e: any) {
      setError(e?.message || "Failed to switch variant");
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="mb-3 rounded-lg border border-border/50 bg-muted/20 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </span>
        {error && <span className="text-xs text-destructive">{error}</span>}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {variants.map((v) => {
          const isLocked = !!v.locked;
          const isBusy = busyKey === v.variant;
          const label = v.label || v.variant;
          return (
            <button
              key={v.variant}
              type="button"
              disabled={isLocked || !!busyKey || disabled}
              onClick={() => handleSelect(v.variant, isLocked)}
              className={[
                "relative flex flex-col items-start rounded-md border p-2 text-left text-xs transition",
                isLocked
                  ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                  : "border-border/60 hover:border-primary/60 hover:bg-accent/30",
                busyKey && !isBusy ? "opacity-60" : "",
              ].join(" ")}
              aria-pressed={isLocked}
            >
              <div className="mb-1 flex w-full items-center justify-between gap-2">
                <span className="font-semibold capitalize">{label}</span>
                {isLocked && (
                  <span className="rounded-sm bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
                    Active
                  </span>
                )}
                {isBusy && (
                  <span className="text-[10px] text-muted-foreground">Switching…</span>
                )}
              </div>
              <p className="text-[11px] leading-snug text-muted-foreground line-clamp-3">
                {_preview(v.content)}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
