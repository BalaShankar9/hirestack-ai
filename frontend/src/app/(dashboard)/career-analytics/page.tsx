"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { CareerSnapshot } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  TrendingUp, Loader2, Camera, Calendar, BarChart3, Target,
  Award, Activity, ArrowUp, ArrowDown, Minus, ChevronDown,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function CareerAnalyticsPage() {
  const { user, session: authSession } = useAuth();

  useEffect(() => { if (authSession?.access_token) api.setToken(authSession.access_token); }, [authSession?.access_token]);

  const [timeline, setTimeline] = useState<CareerSnapshot[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [t, p] = await Promise.all([api.career.timeline(), api.career.portfolio()]);
      setTimeline(t || []);
      setPortfolio(p);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const captureSnapshot = async () => {
    setCapturing(true);
    try {
      await api.career.snapshot();
      await loadData();
      toast({ title: "Snapshot captured!" });
    } catch (e: any) { setError(e.message); }
    finally { setCapturing(false); }
  };

  // Compute trends
  const recent = timeline.slice(-5);
  const trend = recent.length >= 2
    ? (recent[recent.length - 1]?.overall_score || 0) - (recent[0]?.overall_score || 0)
    : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-glow-sm">
            <Activity className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Progress</h1>
            <p className="text-sm text-muted-foreground">Track your career growth over time</p>
          </div>
        </div>
        <Button onClick={captureSnapshot} disabled={capturing} className="rounded-xl gap-2">
          {capturing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
          Capture Snapshot
        </Button>
      </div>

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-48 rounded-2xl" />
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { icon: BarChart3, label: "Applications", value: portfolio?.total_applications || 0, color: "text-blue-500 bg-blue-500/10" },
              { icon: Target, label: "Avg Match", value: `${portfolio?.avg_match_score || 0}%`, color: "text-emerald-500 bg-emerald-500/10" },
              { icon: Award, label: "Documents", value: portfolio?.total_documents || 0, color: "text-amber-500 bg-amber-500/10" },
              { icon: Calendar, label: "Snapshots", value: timeline.length, color: "text-violet-500 bg-violet-500/10" },
              { icon: trend > 0 ? ArrowUp : trend < 0 ? ArrowDown : Minus, label: "Trend",
                value: trend > 0 ? `+${trend}%` : `${trend}%`,
                color: trend > 0 ? "text-emerald-500 bg-emerald-500/10" : trend < 0 ? "text-rose-500 bg-rose-500/10" : "text-muted-foreground bg-muted" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border bg-card p-3 hover:shadow-soft-sm transition-shadow">
                <div className="flex items-center gap-2 mb-1">
                  <div className={cn("flex h-7 w-7 items-center justify-center rounded-lg", s.color)}><s.icon className="h-3.5 w-3.5" /></div>
                  <span className="text-2xs text-muted-foreground">{s.label}</span>
                </div>
                <p className="text-xl font-bold tabular-nums">{s.value}</p>
              </div>
            ))}
          </div>

          {/* Score Chart */}
          {timeline.length > 0 && (
            <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
              <h2 className="font-semibold text-sm mb-4 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-indigo-500" /> Score Evolution</h2>
              <div className="relative h-44">
                <div className="flex items-end gap-[2px] h-full">
                  {timeline.slice(-30).map((s, i) => {
                    const score = s.overall_score || 0;
                    const color = score >= 80 ? "bg-emerald-500" : score >= 60 ? "bg-amber-500" : "bg-rose-500";
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center justify-end group relative h-full">
                        <div className="hidden group-hover:flex absolute -top-10 bg-foreground text-background text-[10px] px-2 py-1 rounded whitespace-nowrap z-10 items-center gap-1 font-mono">
                          {score}% · {new Date(s.snapshot_date || "").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                        </div>
                        <div className={cn("w-full rounded-t-sm transition-all duration-300 hover:opacity-80", color)}
                          style={{ height: `${Math.max(4, score)}%` }} />
                      </div>
                    );
                  })}
                </div>
                {/* Gridlines */}
                <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
                  {[100, 75, 50, 25].map((v) => (
                    <div key={v} className="flex items-center">
                      <span className="text-[9px] text-muted-foreground/40 w-6 text-right mr-1 font-mono">{v}</span>
                      <div className="flex-1 border-t border-dashed border-border/30" />
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex justify-between text-[9px] text-muted-foreground mt-1 font-mono">
                <span>← Oldest</span>
                <span>Most Recent →</span>
              </div>
            </div>
          )}

          {/* Timeline */}
          {timeline.length > 0 && (
            <div className="rounded-2xl border bg-card p-5 shadow-soft-sm">
              <h2 className="font-semibold text-sm mb-3">Snapshot History</h2>
              <div className="space-y-2">
                {timeline.slice().reverse().slice(0, 10).map((s, i) => {
                  const score = s.overall_score || 0;
                  return (
                    <details key={i} className="group rounded-xl border hover:border-primary/20 transition-colors">
                      <summary className="flex items-center gap-3 px-3 py-2 cursor-pointer list-none select-none">
                        <div className={cn("h-3 w-3 rounded-full shrink-0",
                          score >= 80 ? "bg-emerald-500" : score >= 60 ? "bg-amber-500" : "bg-rose-500")} />
                        <span className="text-xs text-muted-foreground flex-1">
                          {new Date(s.snapshot_date || "").toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })}
                        </span>
                        <span className={cn("text-sm font-bold tabular-nums",
                          score >= 80 ? "text-emerald-500" : score >= 60 ? "text-amber-500" : "text-rose-500")}>{score}%</span>
                        <ChevronDown className="h-3 w-3 text-muted-foreground transition-transform group-open:rotate-180" />
                      </summary>
                      <div className="px-3 pb-3 pt-1 border-t flex flex-wrap gap-2">
                        {s.technical_score != null && <Badge variant="outline" className="text-[10px]">Technical: {s.technical_score}</Badge>}
                        {s.experience_score != null && <Badge variant="outline" className="text-[10px]">Experience: {s.experience_score}</Badge>}
                        {s.education_score != null && <Badge variant="outline" className="text-[10px]">Education: {s.education_score}</Badge>}
                        {s.avg_ats_score != null && <Badge variant="outline" className="text-[10px]">Avg ATS: {s.avg_ats_score}</Badge>}
                        {s.applications_count != null && <Badge variant="secondary" className="text-[10px]">{s.applications_count} apps</Badge>}
                      </div>
                    </details>
                  );
                })}
              </div>
            </div>
          )}

          {/* Empty state */}
          {timeline.length === 0 && (
            <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
              <Activity className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
              <h3 className="font-semibold text-sm">No snapshots yet</h3>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">Capture your first snapshot to start tracking your career growth over time.</p>
              <Button className="mt-4 rounded-xl gap-2" onClick={captureSnapshot} disabled={capturing}>
                <Camera className="h-4 w-4" /> Capture First Snapshot
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
