"use client";

import { memo, useState } from "react";
import { ShieldAlert, ShieldCheck, ChevronDown, ChevronUp, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ValidationReport } from "@/lib/firestore/models";

const SEVERITY_CONFIG: Record<string, { color: string; icon: typeof AlertTriangle }> = {
  critical: { color: "text-destructive", icon: ShieldAlert },
  high: { color: "text-orange-600", icon: AlertTriangle },
  medium: { color: "text-amber-500", icon: Info },
  low: { color: "text-muted-foreground", icon: Info },
};

interface ValidationDrawerProps {
  report: ValidationReport | null;
}

export const ValidationDrawer = memo(function ValidationDrawer({
  report,
}: ValidationDrawerProps) {
  const [expanded, setExpanded] = useState(false);

  if (!report) return null;

  const hardFailures = report.issues.filter(
    (i) => i.severity === "critical" || i.severity === "high"
  );
  const softWarnings = report.issues.filter(
    (i) => i.severity === "medium" || i.severity === "low"
  );

  return (
    <div className="space-y-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
      >
        <div className="flex items-center gap-1.5">
          {report.valid ? (
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <ShieldAlert className="h-3.5 w-3.5 text-destructive" />
          )}
          <span>Validation</span>
          {!report.valid && (
            <span className="text-[10px] font-medium text-destructive">
              {report.hard_failures} failure{report.hard_failures !== 1 ? "s" : ""}
            </span>
          )}
          {report.valid && report.soft_warnings > 0 && (
            <span className="text-[10px] font-medium text-amber-500">
              {report.soft_warnings} warning{report.soft_warnings !== 1 ? "s" : ""}
            </span>
          )}
          {report.valid && report.soft_warnings === 0 && (
            <span className="text-[10px] font-medium text-emerald-600">Passed</span>
          )}
        </div>
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {/* Checks summary always visible */}
      <div className="flex flex-wrap gap-1">
        {Object.entries(report.checks).map(([check, passed]) => (
          <span
            key={check}
            className={cn(
              "inline-flex items-center text-[10px] px-1.5 py-0.5 rounded",
              passed
                ? "bg-emerald-50 text-emerald-700"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {passed ? "✓" : "✗"} {check.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {expanded && (
        <div className="space-y-1.5 max-h-48 overflow-y-auto">
          {hardFailures.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-destructive mb-0.5">
                Hard Failures ({hardFailures.length})
              </div>
              {hardFailures.map((issue, i) => {
                const config = SEVERITY_CONFIG[issue.severity] ?? SEVERITY_CONFIG.medium;
                const Icon = config.icon;
                return (
                  <div key={i} className="flex items-start gap-1.5 text-[10px] py-0.5">
                    <Icon className={cn("h-3 w-3 mt-0.5 flex-shrink-0", config.color)} />
                    <div>
                      <span className="font-medium">{issue.field}:</span>{" "}
                      <span className="text-muted-foreground">{issue.message}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {softWarnings.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-amber-500 mb-0.5">
                Warnings ({softWarnings.length})
              </div>
              {softWarnings.map((issue, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] py-0.5">
                  <Info className="h-3 w-3 mt-0.5 flex-shrink-0 text-muted-foreground" />
                  <div>
                    <span className="font-medium">{issue.field}:</span>{" "}
                    <span className="text-muted-foreground">{issue.message}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
