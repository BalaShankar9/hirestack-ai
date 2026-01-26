"use client";

import { ExternalLink, FileText, Tag, Wrench, Sparkles } from "lucide-react";
import type { EvidenceDoc } from "@/lib/firestore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EvidenceCard({
  evidence,
  onUse,
  onOpen,
}: {
  evidence: EvidenceDoc;
  onUse?: (evidence: EvidenceDoc) => void;
  onOpen?: (evidence: EvidenceDoc) => void;
}) {
  const link = evidence.kind === "link" ? evidence.url : evidence.storageUrl;

  return (
    <div className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">{evidence.title}</div>
          {evidence.description ? (
            <div className="mt-1 text-xs text-muted-foreground leading-snug">
              {evidence.description}
            </div>
          ) : null}
        </div>
        <div
          className={cn(
            "h-10 w-10 rounded-xl flex items-center justify-center",
            evidence.kind === "link"
              ? "bg-blue-50 text-blue-700"
              : "bg-purple-50 text-purple-700"
          )}
        >
          {evidence.kind === "link" ? (
            <ExternalLink className="h-4 w-4" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
        </div>
      </div>

      {(evidence.skills.length > 0 || evidence.tools.length > 0 || evidence.tags.length > 0) && (
        <div className="mt-3 space-y-2">
          {evidence.skills.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              <div className="mr-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Tag className="h-3 w-3" /> Skills
              </div>
              {evidence.skills.slice(0, 6).map((s) => (
                <Badge key={s} variant="secondary" className="text-[11px]">
                  {s}
                </Badge>
              ))}
            </div>
          ) : null}
          {evidence.tools.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              <div className="mr-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Wrench className="h-3 w-3" /> Tools
              </div>
              {evidence.tools.slice(0, 6).map((s) => (
                <Badge key={s} variant="secondary" className="text-[11px]">
                  {s}
                </Badge>
              ))}
            </div>
          ) : null}
          {evidence.tags.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              <div className="mr-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Sparkles className="h-3 w-3" /> Tags
              </div>
              {evidence.tags.slice(0, 6).map((s) => (
                <Badge key={s} variant="secondary" className="text-[11px]">
                  {s}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <Button variant="default" size="sm" className="flex-1" onClick={() => onUse?.(evidence)} disabled={!onUse}>
          Use in CV
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            if (onOpen) return onOpen(evidence);
            if (link) window.open(link, "_blank", "noopener,noreferrer");
          }}
        >
          Open
        </Button>
      </div>
    </div>
  );
}

