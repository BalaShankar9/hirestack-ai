"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, Loader2, RefreshCw } from "lucide-react";

import { useAuth } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import api from "@/lib/api";
import {
  type Mission,
  type MissionDraft,
  type MissionSyncSummary,
  type MissionDraftColumn,
  type MissionDraftStatus,
  fitFloorLabel,
  formatCompBand,
  formatRelativeDate,
  missionDraftColumn,
  missionDraftStatusLabel,
  missionDraftStatusVariant,
  missionStatusVariant,
  voicePresetLabel,
} from "@/lib/missions";

type DraftListResponse = { items: MissionDraft[]; count: number; mission_id: string };

const COLUMN_META: Array<{
  key: Exclude<MissionDraftColumn, "closed">;
  title: string;
  body: string;
}> = [
  {
    key: "surfaced",
    title: "Surfaced overnight",
    body: "Newly surfaced candidates that still need your review pass.",
  },
  {
    key: "review",
    title: "Drafted, awaiting your review",
    body: "Prepared workspaces that are ready for your manual send decision.",
  },
  {
    key: "in_flight",
    title: "In flight",
    body: "Rows you have already moved forward after the human-in-the-loop send step.",
  },
];

export default function MissionInboxPage() {
  const params = useParams<{ id: string }>();
  const missionId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const { session } = useAuth();

  const [mission, setMission] = useState<Mission | null>(null);
  const [drafts, setDrafts] = useState<MissionDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyDraftId, setBusyDraftId] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<MissionSyncSummary | null>(null);

  const setToken = () => {
    if (session?.access_token) api.setToken(session.access_token);
  };

  async function loadData(options?: { syncFirst?: boolean }) {
    if (!missionId) return;
    setToken();
    let syncError: string | null = null;
    if (options?.syncFirst) {
      try {
        const summary = (await api.missions.sync(missionId)) as MissionSyncSummary;
        setSyncSummary(summary);
      } catch (err) {
        syncError = err instanceof Error ? err.message : "Failed to sync mission inbox";
      }
    }
    const [missionRow, draftRows] = await Promise.all([
      api.missions.get(missionId) as Promise<Mission>,
      api.missions.listDrafts(missionId, 200) as Promise<DraftListResponse>,
    ]);
    setMission(missionRow);
    setDrafts(Array.isArray(draftRows?.items) ? draftRows.items : []);
    if (syncError) {
      setError(syncError);
    }
  }

  useEffect(() => {
    if (!session?.access_token || !missionId) return;
    setLoading(true);
    setError(null);
    loadData({ syncFirst: true })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load mission inbox");
      })
      .finally(() => setLoading(false));
  }, [session?.access_token, missionId]);

  async function refresh() {
    setRefreshing(true);
    setError(null);
    try {
      await loadData({ syncFirst: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh mission inbox");
    } finally {
      setRefreshing(false);
    }
  }

  async function patchDraftStatus(draft: MissionDraft, status: MissionDraftStatus) {
    if (!missionId) return;
    setBusyDraftId(draft.id);
    setError(null);
    try {
      setToken();
      const updated = (await api.missions.updateDraft(missionId, draft.id, { status })) as MissionDraft;
      setDrafts((current) => current.map((item) => (item.id === draft.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update draft status");
    } finally {
      setBusyDraftId(null);
    }
  }

  const groupedDrafts = useMemo(() => {
    return drafts.reduce<Record<MissionDraftColumn, MissionDraft[]>>(
      (acc, draft) => {
        acc[missionDraftColumn(draft.status)].push(draft);
        return acc;
      },
      { surfaced: [], review: [], in_flight: [], closed: [] },
    );
  }, [drafts]);

  const syncSummaryText = useMemo(() => {
    if (!syncSummary) return null;
    return `Last sync scanned ${syncSummary.scanned_applications} applications, matched ${syncSummary.matched_applications}, created ${syncSummary.created}, and updated ${syncSummary.updated}.`;
  }, [syncSummary]);

  if (!missionId) {
    return <div className="p-6 text-sm text-destructive">Missing mission id.</div>;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-[28px] border border-border/60 bg-gradient-to-br from-background via-background to-primary/5 p-6 shadow-soft-md">
        <div className="space-y-3">
          <Link href="/missions" className="text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="mr-1 inline h-4 w-4" />
            Back to missions
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl font-semibold tracking-tight">{mission?.name ?? "Mission inbox"}</h1>
              {mission ? <Badge variant={missionStatusVariant(mission.status)}>{mission.status}</Badge> : null}
            </div>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              Human-in-the-loop only. Review each surfaced workspace, open the linked application when it exists,
              and only mark a row sent after you have manually completed the actual send step.
            </p>
            {syncSummaryText ? <p className="mt-2 text-xs text-muted-foreground">{syncSummaryText}</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={refresh} loading={refreshing}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button asChild>
            <Link href="/missions/new">
              New mission
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-border/70 bg-card/40">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !mission ? (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          Mission not found.
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Review queue</CardDescription>
                <CardTitle className="text-3xl">{groupedDrafts.review.length}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Surfaced</CardDescription>
                <CardTitle className="text-3xl">{groupedDrafts.surfaced.length}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>In flight</CardDescription>
                <CardTitle className="text-3xl">{groupedDrafts.in_flight.length}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Mission brief</CardDescription>
                <CardTitle className="text-xl">{fitFloorLabel(Number(mission.min_fit_score || 0))}</CardTitle>
                <CardDescription>{formatCompBand(mission.comp_band_min, mission.comp_band_max)} · {voicePresetLabel(mission.voice_preset)}</CardDescription>
              </CardHeader>
            </Card>
          </div>

          {drafts.length === 0 ? (
            <EmptyState
              icon={ExternalLink}
              title="No surfaced drafts yet"
              description="Nothing in your current application corpus matches this mission yet. Refresh runs a real sync against scored applications and will surface any matching rows here."
              actionLabel="Back to missions"
              actionHref="/missions"
              secondaryLabel="Create another mission"
              secondaryHref="/missions/new"
              variant="dashed"
            />
          ) : (
            <div className="grid gap-5 xl:grid-cols-3">
              {COLUMN_META.map((column) => (
                <Card key={column.key} className="border-border/70">
                  <CardHeader className="border-b border-border/50">
                    <CardTitle className="text-xl">{column.title}</CardTitle>
                    <CardDescription>{column.body}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4 p-5">
                    {groupedDrafts[column.key].length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
                        Nothing in this column yet.
                      </div>
                    ) : (
                      groupedDrafts[column.key].map((draft) => (
                        <div key={draft.id} className="rounded-2xl border border-border/60 bg-card/60 p-4">
                          {(() => {
                            const application = draft.application;
                            const headline = application?.role_title || application?.title || (draft.application_id ? `Workspace ${draft.application_id.slice(0, 8)}` : "Application pending link");
                            const companyName = application?.company_name || "Unknown company";
                            const fitScore = draft.fit_score ?? application?.fit_score;
                            const applicationStatus = application?.status ? application.status.replace(/_/g, " ") : null;
                            return (
                              <>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <Badge variant={missionDraftStatusVariant(draft.status)}>{missionDraftStatusLabel(draft.status)}</Badge>
                            {fitScore != null ? (
                              <Badge variant="outline">{Number(fitScore).toFixed(1)}/5 fit</Badge>
                            ) : null}
                          </div>
                          <div className="mt-3 space-y-2 text-sm">
                            <div className="font-medium">{headline}</div>
                            <div className="text-muted-foreground">{companyName}</div>
                            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                              {applicationStatus ? <span>Application {applicationStatus}</span> : null}
                              {application?.ready_to_apply ? <span>Ready assets attached</span> : null}
                              {application?.generated_document_count ? <span>{application.generated_document_count} generated docs</span> : null}
                            </div>
                            <div className="text-muted-foreground">Surfaced {formatRelativeDate(draft.surfaced_at)}</div>
                            {draft.prepared_at ? <div className="text-muted-foreground">Prepared {formatRelativeDate(draft.prepared_at)}</div> : null}
                            {draft.sent_at ? <div className="text-muted-foreground">Sent {formatRelativeDate(draft.sent_at)}</div> : null}
                          </div>
                          <div className="mt-4 flex flex-wrap gap-2">
                            {draft.application_id ? (
                              <Button asChild size="sm">
                                <Link href={`/applications/${draft.application_id}`}>
                                  Open workspace
                                  <ExternalLink className="ml-2 h-4 w-4" />
                                </Link>
                              </Button>
                            ) : null}
                            {draft.status === "surfaced" ? (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={busyDraftId === draft.id}
                                onClick={() => patchDraftStatus(draft, "ready_for_user")}
                              >
                                Mark ready
                              </Button>
                            ) : null}
                            {(draft.status === "prepared" || draft.status === "ready_for_user") ? (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={busyDraftId === draft.id}
                                onClick={() => patchDraftStatus(draft, "sent")}
                              >
                                Mark sent
                              </Button>
                            ) : null}
                            {draft.status !== "sent" && draft.status !== "skipped" && draft.status !== "expired" ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={busyDraftId === draft.id}
                                onClick={() => patchDraftStatus(draft, "skipped")}
                              >
                                Skip
                              </Button>
                            ) : null}
                          </div>
                              </>
                            );
                          })()}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {groupedDrafts.closed.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Closed out</CardTitle>
                <CardDescription>{groupedDrafts.closed.length} rows are already skipped or expired.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {groupedDrafts.closed.map((draft) => (
                  <Badge key={draft.id} variant={missionDraftStatusVariant(draft.status)}>
                    {missionDraftStatusLabel(draft.status)} · {draft.application?.company_name || draft.application?.role_title || (draft.application_id ? draft.application_id.slice(0, 8) : draft.id.slice(0, 8))}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}