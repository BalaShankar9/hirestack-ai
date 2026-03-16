"use client";

import { cn } from "@/lib/utils";

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
}

export function LoadingSkeleton({ lines = 3, className = "" }: LoadingSkeletonProps) {
  return (
    <div aria-live="polite" aria-label="Loading content" className={cn("space-y-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted animate-pulse"
          style={{ width: `${85 - i * 15}%` }}
        />
      ))}
    </div>
  );
}
