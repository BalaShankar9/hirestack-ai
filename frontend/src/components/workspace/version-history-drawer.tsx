"use client";

import { useState } from "react";
import { Clock, RotateCcw, Save, Loader2, Check } from "lucide-react";
import type { DocVersion } from "@/lib/firestore";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";

function formatTime(ms: number) {
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(ms);
  }
}

export function VersionHistoryDrawer({
  open,
  onOpenChange,
  versions = [],
  onSnapshot,
  onRestore,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  versions?: DocVersion[];
  onSnapshot: (label: string) => void;
  onRestore: (versionId: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const handleSnapshot = async () => {
    setSaving(true);
    try {
      await onSnapshot(`Snapshot ${new Date().toLocaleTimeString()}`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async (versionId: string) => {
    setRestoringId(versionId);
    try {
      await onRestore(versionId);
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[460px]">
        <SheetHeader>
          <SheetTitle>Version history</SheetTitle>
          <SheetDescription>
            Snapshot versions so you can iterate safely and compare outcomes.
          </SheetDescription>
          <div className="mt-4 flex items-center gap-2">
            <Button
              size="sm"
              className="gap-2 rounded-xl"
              disabled={saving}
              onClick={handleSnapshot}
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : saved ? (
                <Check className="h-4 w-4 text-emerald-500" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {saving ? "Saving…" : saved ? "Saved!" : "Save snapshot"}
            </Button>
          </div>
        </SheetHeader>

        <Separator />

        <SheetBody className="pt-4">
          {versions.length === 0 ? (
            <div className="rounded-xl bg-muted/40 p-4">
              <div className="text-sm font-medium">No versions yet.</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Save a snapshot after each meaningful change (before regenerations, before exporting).
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {versions.map((v) => (
                <div key={v.id} className="rounded-xl border bg-card p-3 transition-all duration-200 hover:shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate">{v.label}</div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        {formatTime(v.createdAt)}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-2"
                      disabled={restoringId === v.id}
                      onClick={() => handleRestore(v.id)}
                    >
                      {restoringId === v.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                      {restoringId === v.id ? "Restoring…" : "Restore"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

