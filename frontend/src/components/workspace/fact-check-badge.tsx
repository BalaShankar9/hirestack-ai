"use client";

import { memo } from "react";
import { ShieldCheck, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface FactCheckBadgeProps {
  verified: number;
  enhanced: number;
  fabricated: number;
  className?: string;
}

export const FactCheckBadge = memo(function FactCheckBadge({
  verified,
  enhanced,
  fabricated,
  className,
}: FactCheckBadgeProps) {
  const total = verified + enhanced + fabricated;
  const accuracy = total > 0 ? Math.round(((verified + enhanced) / total) * 100) : 100;

  return (
    <div className={cn("inline-flex items-center gap-2 px-3 py-1.5 rounded-lg", className,
      fabricated > 0 ? "bg-destructive/10 border border-destructive/20" : "bg-emerald-500/10 border border-emerald-500/20"
    )}>
      {fabricated > 0 ? (
        <ShieldAlert className="h-4 w-4 text-destructive" />
      ) : (
        <ShieldCheck className="h-4 w-4 text-emerald-600" />
      )}
      <span className="font-mono text-xs font-medium">
        {verified} verified · {enhanced} enhanced
        {fabricated > 0 && <span className="text-destructive"> · {fabricated} fabricated</span>}
      </span>
      <span className="font-mono text-xs text-muted-foreground">({accuracy}%)</span>
    </div>
  );
});
