"use client";

import Link from "next/link";
import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, Loader2, PauseCircle, PlayCircle, RefreshCw, Target, Zap } from "lucide-react";

import { useAuth } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import api from "@/lib/api";
import {
  type Mission,
  type MissionStatus,
  fitFloorLabel,
  formatCompBand,
  formatRelativeDate,
  missionStatusVariant,
  parseMissionListInput,
  voicePresetLabel,
} from "@/lib/missions";

type MissionListResponse = { items: Mission[]; count: number };

const FILTERS: Array<{ value: "all" | MissionStatus; label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

export default function MissionsPage() {
  const { session } = useAuth();
  const [missions, setMissions] = useState<Mission[]>([]);
  const [filter, setFilter] = useState<"all" | MissionStatus>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyMissionId, setBusyMissionId] = useState<string | null>(null);

  const setToken = () => {
    if (session?.access_token) api.setToken(session.access_token);
  };

  async function loadMissions() {
    setError(null);
    setToken();
    const res = (await api.missions.list()) as MissionListResponse;
    setMissions(Array.isArray(res?.items) ? res.items : []);
  }

  useEffect(() => {
    if (!session?.access_token) return;
    setLoading(true);
    loadMissions()
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load missions");
      })
      .finally(() => setLoading(false));
  }, [session?.access_token]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await loadMissions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh missions");
    } finally {
      setRefreshing(false);
    }
  }

  async function patchStatus(mission: Mission, status: MissionStatus) {
    setBusyMissionId(mission.id);
    setError(null);
    try {
      setToken();
      const updated = (await api.missions.update(mission.id, { status })) as Mission;
      setMissions((current) => current.map((item) => (item.id === mission.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update mission");
    } finally {
      setBusyMissionId(null);
    }
  }

  const filtered = useMemo(() => {
    if (filter === "all") return missions;
    return missions.filter((mission) => mission.status === filter);
  }, [filter, missions]);

  const summary = useMemo(
    () => ({
      active: missions.filter((mission) => mission.status === "active").length,
      paused: missions.filter((mission) => mission.status === "paused").length,
      archived: missions.filter((mission) => mission.status === "archived").length,
      weeklyTarget: missions.reduce((sum, mission) => sum + Number(mission.target_volume_per_week || 0), 0),
    }),
    [missions],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-col gap-4 rounded-[28px] border border-border/60 bg-gradient-to-br from-background via-background to-primary/5 p-6 shadow-soft-md md:flex-row md:items-end md:justify-between">
        <div className="space-y-3">
          <Badge variant="premium" className="w-fit gap-1.5 px-3 py-1 text-[11px] uppercase tracking-[0.2em]">
            <Zap className="h-3.5 w-3.5" />
            Mission Mode
          </Badge>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Focused search tracks</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Missions turn your role targets, guardrails, and fit floor into a reusable operating brief.
              Start with the setup flow, then use each mission inbox to review surfaced workspaces without diluting your search.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={handleRefresh} loading={refreshing}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button asChild>
            <Link href="/missions/new">
              Create mission
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active</CardDescription>
            <CardTitle className="text-3xl">{summary.active}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Paused</CardDescription>
            <CardTitle className="text-3xl">{summary.paused}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Archived</CardDescription>
            <CardTitle className="text-3xl">{summary.archived}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Weekly target</CardDescription>
            <CardTitle className="text-3xl">{summary.weeklyTarget}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((option) => (
          <Button
            key={option.value}
            variant={filter === option.value ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </Button>
        ))}
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
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Target}
          title={missions.length === 0 ? "No missions yet" : "No missions in this filter"}
          description={
            missions.length === 0
              ? "Create your first mission to lock in the roles, locations, compensation band, and fit floor you actually want to run. Missions are the stable input contract for the inbox and orchestration layers that come next."
              : "This filter is empty right now. Switch filters or create a new mission for another search track."
          }
          actionLabel="Create mission"
          actionHref="/missions/new"
          secondaryLabel={missions.length === 0 ? "Open tracked companies" : undefined}
          secondaryHref={missions.length === 0 ? "/tracked-companies" : undefined}
          variant="dashed"
        />
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          {filtered.map((mission) => {
            const roles = mission.role_titles.length > 0 ? mission.role_titles : ["No role titles yet"];
            const locations = mission.locations.length > 0 ? mission.locations : ["Open location search"];
            const rolePreview = parseMissionListInput(roles.join(", ")).slice(0, 3);

            return (
              <Card key={mission.id} className="overflow-hidden border-border/70">
                <CardHeader className="gap-4 border-b border-border/50 bg-gradient-to-r from-background to-primary/5">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-2xl">{mission.name}</CardTitle>
                        <Badge variant={missionStatusVariant(mission.status)}>{mission.status}</Badge>
                      </div>
                      <CardDescription>
                        {fitFloorLabel(Number(mission.min_fit_score || 0))} · {voicePresetLabel(mission.voice_preset)} · {mission.target_volume_per_week} roles/week
                      </CardDescription>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button asChild size="sm">
                        <Link href={`/missions/${mission.id}`}>
                          Open inbox
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Link>
                      </Button>
                      {mission.status !== "archived" && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyMissionId === mission.id}
                          onClick={() => patchStatus(mission, mission.status === "paused" ? "active" : "paused")}
                        >
                          {mission.status === "paused" ? (
                            <PlayCircle className="mr-2 h-4 w-4" />
                          ) : (
                            <PauseCircle className="mr-2 h-4 w-4" />
                          )}
                          {mission.status === "paused" ? "Resume" : "Pause"}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5 p-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Role focus</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {rolePreview.map((role) => (
                          <Badge key={role} variant="outline" className="bg-background/70">{role}</Badge>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Locations</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {locations.slice(0, 3).map((location) => (
                          <Badge key={location} variant="outline" className="bg-background/70">{location}</Badge>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Comp band</div>
                      <div className="mt-2 text-sm font-medium">{formatCompBand(mission.comp_band_min, mission.comp_band_max)}</div>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Must-haves</div>
                      <div className="mt-2 text-sm font-medium">{mission.must_haves.length || 0}</div>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Created</div>
                      <div className="mt-2 text-sm font-medium">{formatRelativeDate(mission.created_at)}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}