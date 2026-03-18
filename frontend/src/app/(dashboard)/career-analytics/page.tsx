"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { CareerSnapshot } from "@/types";
import { Button } from "@/components/ui/button";
import { TrendingUp, Loader2, Camera, Calendar, BarChart3, Target, Award } from "lucide-react";

export default function CareerAnalyticsPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;
  const [timeline, setTimeline] = useState<CareerSnapshot[]>([]);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [timelineRes, portfolioRes] = await Promise.all([
        api.career.timeline(),
        api.career.portfolio(),
      ]);
      setTimeline(timelineRes || []);
      setPortfolio(portfolioRes);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const captureSnapshot = async () => {
    setCapturing(true);
    try {
      await api.career.snapshot();
      loadData();
    } catch (e: any) {
      setError(e.message || "Capture failed");
    } finally {
      setCapturing(false);
    }
  };

  return (
    <div className="space-y-8 p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/10">
            <TrendingUp className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Career Analytics</h1>
            <p className="text-xs text-muted-foreground">Track your career readiness over time</p>
          </div>
        </div>
        <Button onClick={captureSnapshot} disabled={capturing}>
          {capturing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Camera className="h-4 w-4 mr-2" />}
          Capture Snapshot
        </Button>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* Portfolio Summary */}
          {portfolio && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard icon={<BarChart3 className="h-6 w-6 text-blue-500 dark:text-blue-400" />} label="Applications" value={portfolio.total_applications || 0} />
              <StatCard icon={<Target className="h-6 w-6 text-green-500 dark:text-green-400" />} label="Avg. Match Score" value={`${portfolio.avg_match_score || 0}%`} />
              <StatCard icon={<Award className="h-6 w-6 text-yellow-500 dark:text-yellow-400" />} label="Documents" value={portfolio.total_documents || 0} />
              <StatCard icon={<TrendingUp className="h-6 w-6 text-purple-500 dark:text-purple-400" />} label="Snapshots" value={timeline.length} />
            </div>
          )}

          {/* Score Trends */}
          {timeline.length > 0 && (
            <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Calendar className="h-5 w-5" /> Score Timeline
              </h2>

              {/* Simple chart using bars */}
              <div className="space-y-3">
                <div className="flex items-end gap-1 h-40">
                  {timeline.slice(-20).map((s, i) => {
                    const score = s.overall_score || 0;
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                        <div className="hidden group-hover:block absolute -top-8 bg-foreground text-background text-xs px-2 py-1 rounded whitespace-nowrap z-10">
                          {score}% — {new Date(s.snapshot_date || "").toLocaleDateString()}
                        </div>
                        <div
                          className={`w-full rounded-t transition-all ${
                            score >= 80 ? "bg-green-500" : score >= 60 ? "bg-yellow-500" : "bg-red-500"
                          }`}
                          style={{ height: `${Math.max(4, score)}%` }}
                        />
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Oldest</span>
                  <span>Most Recent</span>
                </div>
              </div>
            </div>
          )}

          {/* Timeline Detail */}
          {timeline.length > 0 && (
            <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm">
              <h2 className="text-xl font-semibold">Snapshot History</h2>
              <div className="space-y-4">
                {timeline.slice().reverse().map((s, i) => (
                  <div key={i} className="flex items-center gap-4 p-4 rounded-lg bg-muted/30">
                    {/* Timeline dot */}
                    <div className="flex flex-col items-center shrink-0">
                      <div className={`h-4 w-4 rounded-full ${
                        (s.overall_score || 0) >= 80 ? "bg-green-500" : (s.overall_score || 0) >= 60 ? "bg-yellow-500" : "bg-red-500"
                      }`} />
                      {i < timeline.length - 1 && <div className="w-0.5 h-6 bg-border" />}
                    </div>

                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">
                          {new Date(s.snapshot_date || "").toLocaleDateString("en-US", {
                            year: "numeric", month: "short", day: "numeric",
                          })}
                        </span>
                        <span className={`text-lg font-bold ${
                          (s.overall_score || 0) >= 80 ? "text-green-600 dark:text-green-400" : (s.overall_score || 0) >= 60 ? "text-yellow-600 dark:text-yellow-400" : "text-red-600 dark:text-red-400"
                        }`}>
                          {s.overall_score || 0}%
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {s.technical_score !== undefined && <span className="text-[11px] bg-muted px-2 py-0.5 rounded-lg">Technical: {s.technical_score}</span>}
                        {s.experience_score !== undefined && <span className="text-[11px] bg-muted px-2 py-0.5 rounded-lg">Experience: {s.experience_score}</span>}
                        {s.education_score !== undefined && <span className="text-[11px] bg-muted px-2 py-0.5 rounded-lg">Education: {s.education_score}</span>}
                        {s.avg_ats_score !== undefined && <span className="text-[11px] bg-muted px-2 py-0.5 rounded-lg">Avg ATS: {s.avg_ats_score}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {timeline.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <TrendingUp className="h-16 w-16 mx-auto mb-3 opacity-30" />
              <p>No snapshots yet. Capture your first snapshot to start tracking progress.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border p-4 text-center space-y-2 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
      <div className="flex justify-center">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
