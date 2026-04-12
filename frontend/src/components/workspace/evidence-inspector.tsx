"use client";

import { memo, useState } from "react";
import { Shield, AlertTriangle, CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import type { ClaimCitation, EvidenceSummary } from "@/lib/firestore/models";

const CLASSIFICATION_CONFIG: Record<string, { color: string; icon: typeof CheckCircle2; label: string }> = {
  verified: { color: "text-emerald-600", icon: CheckCircle2, label: "Verified" },
  supported: { color: "text-emerald-500", icon: CheckCircle2, label: "Supported" },
  inferred: { color: "text-blue-500", icon: Shield, label: "Inferred" },
  embellished: { color: "text-amber-500", icon: AlertTriangle, label: "Embellished" },
  fabricated: { color: "text-destructive", icon: XCircle, label: "Fabricated" },
  unsupported: { color: "text-destructive", icon: XCircle, label: "Unsupported" },
};

interface EvidenceInspectorProps {
  citations: ClaimCitation[] | null;
  evidenceSummary: EvidenceSummary | null;
}

export const EvidenceInspector = memo(function EvidenceInspector({
  citations,
  evidenceSummary,
}: EvidenceInspectorProps) {
  const [expanded, setExpanded] = useState(false);

  if (!citations?.length && !evidenceSummary) return null;

  // Group citations by classification
  const grouped: Record<string, ClaimCitation[]> = {};
  for (const c of citations ?? []) {
    const key = c.classification || "unknown";
    (grouped[key] ??= []).push(c);
  }

  const fabricatedCount = evidenceSummary?.fabricated_count ?? (grouped.fabricated?.length ?? 0) + (grouped.unsupported?.length ?? 0);
  const unlinkedCount = evidenceSummary?.unlinked_count ?? 0;
  const totalCitations = citations?.length ?? evidenceSummary?.citation_count ?? 0;

  // Overall health indicator
  const health = fabricatedCount > 0 ? "danger" : unlinkedCount > totalCitations * 0.3 ? "warn" : "good";

  return (
    <div className="space-y-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <Shield className="h-3.5 w-3.5" />
          Evidence & Claims
          <span
            className={`ml-1 inline-block h-2 w-2 rounded-full ${
              health === "danger" ? "bg-destructive" : health === "warn" ? "bg-amber-500" : "bg-emerald-500"
            }`}
          />
        </div>
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {/* Summary row always visible */}
      {evidenceSummary && (
        <div className="grid grid-cols-3 gap-1.5 text-[10px]">
          <div className="rounded-md bg-muted/50 px-2 py-1 text-center">
            <div className="font-semibold tabular-nums">{evidenceSummary.evidence_count}</div>
            <div className="text-muted-foreground">Evidence</div>
          </div>
          <div className="rounded-md bg-muted/50 px-2 py-1 text-center">
            <div className="font-semibold tabular-nums">{totalCitations}</div>
            <div className="text-muted-foreground">Claims</div>
          </div>
          <div className={`rounded-md px-2 py-1 text-center ${fabricatedCount > 0 ? "bg-destructive/10" : "bg-muted/50"}`}>
            <div className={`font-semibold tabular-nums ${fabricatedCount > 0 ? "text-destructive" : ""}`}>
              {fabricatedCount}
            </div>
            <div className="text-muted-foreground">Fabricated</div>
          </div>
        </div>
      )}

      {/* Tier distribution */}
      {expanded && evidenceSummary?.tier_distribution && Object.keys(evidenceSummary.tier_distribution).length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {Object.entries(evidenceSummary.tier_distribution).map(([tier, count]) => (
            <span key={tier} className="inline-flex items-center gap-0.5 text-[10px] rounded-full bg-muted/60 px-2 py-0.5">
              <span className="font-medium">{tier}</span>
              <span className="text-muted-foreground">×{count}</span>
            </span>
          ))}
        </div>
      )}

      {/* Individual claims */}
      {expanded && citations && citations.length > 0 && (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {Object.entries(grouped).map(([classification, claims]) => {
            const config = CLASSIFICATION_CONFIG[classification] ?? {
              color: "text-muted-foreground",
              icon: Shield,
              label: classification,
            };
            const Icon = config.icon;
            return (
              <div key={classification}>
                <div className={`flex items-center gap-1 text-[10px] font-medium ${config.color} mb-0.5`}>
                  <Icon className="h-3 w-3" />
                  {config.label} ({claims.length})
                </div>
                {claims.slice(0, 3).map((claim, i) => (
                  <div key={i} className="text-[10px] text-muted-foreground pl-4 truncate">
                    {claim.claim_text}
                  </div>
                ))}
                {claims.length > 3 && (
                  <div className="text-[10px] text-muted-foreground pl-4 italic">
                    +{claims.length - 3} more
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});
