"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Brain, CheckCircle2 } from "lucide-react";

interface TraceItem {
  label: string;
  value?: string | number;
  done?: boolean;
}

interface AITraceProps {
  /** Compact inline badge showing AI summary */
  items: TraceItem[];
  /** Optional title */
  title?: string;
  /** Visual variant */
  variant?: "inline" | "card" | "banner";
  className?: string;
}

/**
 * AI intelligence trace component.
 * Shows compact, elegant summaries of what AI detected/analyzed.
 * e.g. "Extracted 12 requirements · Detected 3 gaps · Matched 8 evidence items"
 */
export function AITrace({ items, title, variant = "inline", className }: AITraceProps) {
  if (variant === "inline") {
    return (
      <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1", className)}>
        <Brain className="h-3.5 w-3.5 text-primary/70" />
        {items.map((item, i) => (
          <span
            key={i}
            className="flex items-center gap-1 text-xs text-muted-foreground"
          >
            {item.done && <CheckCircle2 className="h-3 w-3 text-emerald-500" />}
            {item.value !== undefined && (
              <span className="font-semibold text-foreground tabular-nums">
                {item.value}
              </span>
            )}
            {item.label}
            {i < items.length - 1 && (
              <span className="ml-2 text-border">·</span>
            )}
          </span>
        ))}
      </div>
    );
  }

  if (variant === "banner") {
    return (
      <div
        className={cn(
          "flex items-center gap-3 rounded-xl border border-primary/10 bg-primary/[0.03] px-4 py-2.5",
          className
        )}
      >
        <Brain className="h-4 w-4 text-primary shrink-0" />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {items.map((item, i) => (
            <span
              key={i}
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              {item.done && <CheckCircle2 className="h-3 w-3 text-emerald-500" />}
              {item.value !== undefined && (
                <span className="font-semibold text-foreground tabular-nums">
                  {item.value}
                </span>
              )}
              {item.label}
            </span>
          ))}
        </div>
      </div>
    );
  }

  // card variant
  return (
    <div className={cn("rounded-xl border bg-card p-4", className)}>
      {title && (
        <div className="flex items-center gap-2 mb-3">
          <Brain className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold">{title}</span>
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded-lg bg-muted/30 px-3 py-2"
          >
            {item.done ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            ) : (
              <div className="h-1.5 w-1.5 rounded-full bg-primary/50 shrink-0" />
            )}
            <span className="text-xs text-muted-foreground">{item.label}</span>
            {item.value !== undefined && (
              <span className="ml-auto text-xs font-semibold tabular-nums">
                {item.value}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
