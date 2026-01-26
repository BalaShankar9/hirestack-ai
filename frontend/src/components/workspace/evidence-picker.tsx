"use client";

import { useMemo, useState } from "react";
import { Search, Sparkles } from "lucide-react";
import type { EvidenceDoc } from "@/lib/firestore";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function EvidencePicker({
  open,
  onOpenChange,
  evidence,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  evidence: EvidenceDoc[];
  onPick: (evidence: EvidenceDoc) => void;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return evidence;
    return evidence.filter((e) => {
      const hay = `${e.title} ${e.description || ""} ${e.skills.join(" ")} ${e.tools.join(" ")} ${e.tags.join(" ")}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [evidence, q]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Select evidence</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by skill, tool, tag, title…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <ScrollArea className="h-[420px] pr-2">
          <div className="space-y-2">
            {filtered.length === 0 ? (
              <div className="rounded-xl bg-muted/40 p-4">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Sparkles className="h-4 w-4 text-blue-600" />
                  No matches.
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Try searching by a missing keyword from your gaps.
                </div>
              </div>
            ) : (
              filtered.map((e) => (
                <button
                  key={e.id}
                  className="w-full rounded-xl border bg-white p-3 text-left hover:bg-muted/40 transition-colors"
                  onClick={() => {
                    onPick(e);
                    onOpenChange(false);
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate">{e.title}</div>
                      {e.description ? (
                        <div className="mt-1 text-xs text-muted-foreground line-clamp-2">
                          {e.description}
                        </div>
                      ) : null}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {e.skills.slice(0, 4).map((s) => (
                          <Badge key={s} variant="secondary" className="text-[11px]">
                            {s}
                          </Badge>
                        ))}
                        {e.tools.slice(0, 3).map((s) => (
                          <Badge key={s} variant="secondary" className="text-[11px]">
                            {s}
                          </Badge>
                        ))}
                        {e.tags.slice(0, 3).map((s) => (
                          <Badge key={s} variant="secondary" className="text-[11px]">
                            {s}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <Button size="sm" variant="outline" className="shrink-0">
                      Use
                    </Button>
                  </div>
                </button>
              ))
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

