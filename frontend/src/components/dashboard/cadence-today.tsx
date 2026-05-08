"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Clock3, Copy, Sparkles } from "lucide-react";

import api from "@/lib/api";
import { toast } from "@/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type CadenceBucket = "urgent" | "overdue" | "waiting" | "cold";

type CadenceItem = {
  application_id: string;
  company: string;
  role: string;
  status: string;
  scheduled_for: string | null;
  days_until: number | null;
  days_overdue: number | null;
  followup_count: number;
  template_key: string | null;
  suggested_channel: string | null;
  reason: string;
  draft_subject: string | null;
  draft_body: string | null;
};

type CadencePayload = {
  date: string;
  buckets: Record<CadenceBucket, CadenceItem[]>;
  metadata: {
    total_tracked: number;
    actionable_count: number;
    urgent_count: number;
    overdue_count: number;
    waiting_count: number;
    cold_count: number;
    closed_count: number;
  };
};

const BUCKET_ORDER: Array<{ key: CadenceBucket; label: string; accent: string }> = [
  { key: "urgent", label: "Urgent", accent: "bg-rose-500/10 text-rose-500 border-rose-500/20" },
  { key: "overdue", label: "Overdue", accent: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  { key: "waiting", label: "Waiting", accent: "bg-sky-500/10 text-sky-500 border-sky-500/20" },
  { key: "cold", label: "Cold", accent: "bg-slate-500/10 text-slate-500 border-slate-500/20" },
];

function bucketPill(bucket: CadenceBucket): string {
  return BUCKET_ORDER.find((entry) => entry.key === bucket)?.accent || "bg-muted text-muted-foreground";
}

function scheduleCopy(item: CadenceItem, bucket: CadenceBucket): string {
  if (bucket === "cold") return `${item.followup_count} follow-ups sent`;
  if (item.days_overdue !== null) {
    return item.days_overdue === 0 ? "Due now" : `${item.days_overdue}d overdue`;
  }
  if (item.days_until !== null) {
    return item.days_until === 0 ? "Due today" : `In ${item.days_until}d`;
  }
  if (!item.scheduled_for) return "Unscheduled";
  return new Date(item.scheduled_for).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

async function copyDraft(item: CadenceItem) {
  const text = [item.draft_subject, item.draft_body].filter(Boolean).join("\n\n");
  if (!text.trim()) {
    toast({ title: "No draft yet", description: "This follow-up does not have a previewable draft yet." });
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast({ title: "Draft copied", description: "Follow-up draft copied to your clipboard." });
  } catch {
    toast({ title: "Copy failed", description: "Clipboard access is unavailable in this browser." });
  }
}

export function CadenceToday({ enabled }: { enabled: boolean }) {
  const [data, setData] = useState<CadencePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    api.cadence.today()
      .then((payload) => {
        if (!cancelled) setData(payload as CadencePayload);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const actionable = useMemo(() => {
    if (!data) return [] as Array<CadenceItem & { bucket: CadenceBucket }>;
    return (["urgent", "overdue"] as const).flatMap((bucket) =>
      data.buckets[bucket].map((item) => ({ ...item, bucket })),
    ).slice(0, 4);
  }, [data]);

  const upcoming = useMemo(() => {
    if (!data) return [] as CadenceItem[];
    return data.buckets.waiting.slice(0, 3);
  }, [data]);

  const cold = useMemo(() => {
    if (!data) return [] as CadenceItem[];
    return data.buckets.cold.slice(0, 3);
  }, [data]);

  if (!enabled) return null;

  return (
    <section className="rounded-3xl border bg-card p-5 shadow-soft-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Clock3 className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Cadence Today</h2>
              <p className="text-xs text-muted-foreground">
                Follow-up queue across active applications.
              </p>
            </div>
          </div>
        </div>
        {data && (
          <div className="flex items-center gap-2 rounded-xl border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            {data.metadata.actionable_count} needing attention · {data.metadata.total_tracked} tracked
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        {BUCKET_ORDER.map((bucket) => (
          <div key={bucket.key} className="rounded-2xl border bg-muted/10 p-3">
            <div className="flex items-center justify-between gap-3">
              <Badge variant="secondary" className={cn("border text-[11px]", bucket.accent)}>
                {bucket.label}
              </Badge>
              <span className="text-lg font-semibold tabular-nums">
                {loading || !data ? "-" : data.metadata[`${bucket.key}_count` as const]}
              </span>
            </div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-3 rounded-2xl border bg-muted/10 p-4">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
          <div className="space-y-3">
            <div className="rounded-2xl border bg-muted/10 p-4"><Skeleton className="h-24 w-full" /></div>
            <div className="rounded-2xl border bg-muted/10 p-4"><Skeleton className="h-24 w-full" /></div>
          </div>
        </div>
      ) : error ? (
        <div className="mt-4 rounded-2xl border border-dashed bg-muted/10 p-4 text-sm text-muted-foreground">
          Cadence is not available right now. The rest of the dashboard is unaffected.
        </div>
      ) : data ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="rounded-2xl border bg-muted/10 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Action queue</h3>
                <p className="text-xs text-muted-foreground">Urgent and overdue follow-ups worth handling first.</p>
              </div>
            </div>

            <div className="mt-3 space-y-3">
              {actionable.length === 0 ? (
                <div className="rounded-xl border border-dashed bg-background/70 p-4 text-sm text-muted-foreground">
                  Nothing urgent today. Upcoming beats are queued below.
                </div>
              ) : actionable.map((item) => (
                <div key={`${item.bucket}-${item.application_id}`} className="rounded-xl border bg-background/80 p-3">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-semibold truncate">{item.company}</p>
                        <Badge variant="secondary" className={cn("border text-[10px] capitalize", bucketPill(item.bucket))}>
                          {item.bucket}
                        </Badge>
                        <span className="text-[11px] text-muted-foreground">{scheduleCopy(item, item.bucket)}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{item.role}</p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.reason}</p>
                      {item.draft_body && (
                        <p className="mt-2 line-clamp-3 text-xs text-foreground/80">
                          {item.draft_body}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button variant="outline" size="sm" className="rounded-xl text-xs" onClick={() => copyDraft(item)}>
                        <Copy className="mr-1.5 h-3 w-3" /> Copy draft
                      </Button>
                      <Button asChild size="sm" className="rounded-xl text-xs">
                        <Link href={`/applications/${item.application_id}`}>
                          Open <ArrowRight className="ml-1.5 h-3 w-3" />
                        </Link>
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border bg-muted/10 p-4">
              <h3 className="text-sm font-semibold">Coming up</h3>
              <div className="mt-3 space-y-3">
                {upcoming.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No scheduled beats in the queue yet.</p>
                ) : upcoming.map((item) => (
                  <div key={`waiting-${item.application_id}`} className="rounded-xl border bg-background/80 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{item.company}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{item.role}</p>
                      </div>
                      <span className="text-[11px] text-muted-foreground">{scheduleCopy(item, "waiting")}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border bg-muted/10 p-4">
              <h3 className="text-sm font-semibold">Cooling off</h3>
              <div className="mt-3 space-y-3">
                {cold.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No applications are in the cold bucket.</p>
                ) : cold.map((item) => (
                  <div key={`cold-${item.application_id}`} className="rounded-xl border bg-background/80 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{item.company}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{item.role}</p>
                      </div>
                      <Badge variant="secondary" className="border bg-slate-500/10 text-[10px] text-slate-500 border-slate-500/20">
                        {item.followup_count} sent
                      </Badge>
                    </div>
                    <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{item.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default CadenceToday;