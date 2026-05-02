"use client";

import { useMemo } from "react";
import { CheckCircle2, AlertTriangle, HelpCircle, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type {
  CandidateValidationReport,
  CandidateValidationClaim,
} from "@/lib/firestore";

/**
 * CandidateValidationPanel — renders the `CandidateValidationReport`
 * produced by ATLAS v2's `ValidationSwarm`. Surfaced via
 * `result.meta.atlas_candidate_validation` in the SSE complete payload
 * (Slice 4.2).
 *
 * Renders `null` when the report is missing or has zero claims, so it
 * can be unconditionally mounted by parents.
 *
 * Display priorities:
 *   • Conflicted claims first (red — actionable)
 *   • Then unverified (amber — informational)
 *   • Then verified (emerald — collapsed by default in dense view)
 */
export function CandidateValidationPanel({
  report,
  className,
}: {
  report?: CandidateValidationReport | null;
  className?: string;
}) {
  const claims = Array.isArray(report?.claims) ? report!.claims : [];
  const verified = report?.verified_count ?? 0;
  const conflicted = report?.conflicted_count ?? 0;

  // Sort: conflicted → unverified → verified
  const sorted = useMemo<CandidateValidationClaim[]>(
    () => [...claims].sort((a, b) => statusRank(a.status) - statusRank(b.status)),
    [claims],
  );

  if (claims.length === 0) return null;

  return (
    <section
      data-testid="atlas-validation-panel"
      className={cn("space-y-3", className)}
      aria-label="Candidate claim validation"
    >
      <header className="flex items-center gap-2">
        <Shield className="h-4 w-4 text-blue-600" aria-hidden />
        <h3 className="text-sm font-semibold tracking-tight">
          Claim validation
        </h3>
        <span
          data-testid="atlas-validation-summary"
          className="text-xs text-muted-foreground"
        >
          ({verified} verified · {conflicted} conflicted · {claims.length} total)
        </span>
      </header>

      <ul className="space-y-1.5">
        {sorted.map((c, i) => (
          <ClaimRow key={`${c.validator}-${i}`} claim={c} />
        ))}
      </ul>
    </section>
  );
}

function statusRank(s: CandidateValidationClaim["status"]): number {
  if (s === "conflicted") return 0;
  if (s === "unverified") return 1;
  return 2; // verified
}

function ClaimRow({ claim }: { claim: CandidateValidationClaim }) {
  const meta = STATUS_META[claim.status] ?? STATUS_META.unverified;

  return (
    <li
      data-testid="atlas-validation-claim"
      data-status={claim.status}
      className={cn(
        "flex items-start gap-2 rounded-md border p-2 text-xs",
        meta.bg,
        meta.border,
      )}
    >
      <span className={cn("mt-0.5 shrink-0", meta.fg)} aria-hidden>
        {meta.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium">{claim.claim || "(no claim text)"}</span>
          <Badge
            variant="secondary"
            className={cn("text-[10px] border", meta.fg, meta.border, meta.bg)}
          >
            {claim.status}
          </Badge>
          <span className="text-[10px] text-muted-foreground">
            via {claim.validator}
          </span>
        </div>
        {claim.detail && (
          <div className="mt-0.5 text-muted-foreground">{claim.detail}</div>
        )}
      </div>
    </li>
  );
}

const STATUS_META: Record<
  CandidateValidationClaim["status"],
  { icon: React.ReactNode; fg: string; bg: string; border: string }
> = {
  verified: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    fg: "text-emerald-700",
    bg: "bg-emerald-500/10",
    border: "border-emerald-200",
  },
  conflicted: {
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
    fg: "text-red-700",
    bg: "bg-red-500/10",
    border: "border-red-200",
  },
  unverified: {
    icon: <HelpCircle className="h-3.5 w-3.5" />,
    fg: "text-amber-700",
    bg: "bg-amber-500/10",
    border: "border-amber-200",
  },
};
