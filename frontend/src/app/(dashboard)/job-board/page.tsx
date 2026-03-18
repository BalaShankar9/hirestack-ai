"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { JobAlert, JobMatch } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, Loader2, Plus, ExternalLink, Star, ThumbsUp, ThumbsDown, Trash2 } from "lucide-react";
import { sanitizeUrl } from "@/lib/sanitize";
import { toast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_COLORS: Record<string, string> = {
  new: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  interested: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  applied: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  saved: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
};

export default function JobBoardPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;
  const [alerts, setAlerts] = useState<JobAlert[]>([]);
  const [matches, setMatches] = useState<JobMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // New alert form
  const [showForm, setShowForm] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [alertLocation, setAlertLocation] = useState("");
  const [salaryMin, setSalaryMin] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [alertsRes, matchesRes] = await Promise.all([
        api.jobSync.getAlerts(),
        api.jobSync.getMatches(),
      ]);
      setAlerts(alertsRes || []);
      setMatches(matchesRes || []);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const createAlert = async () => {
    if (!keywords.trim()) return;
    try {
      await api.jobSync.createAlert({
        keywords: keywords.split(",").map((k) => k.trim()),
        location: alertLocation || undefined,
        salary_min: salaryMin ? parseInt(salaryMin) : undefined,
      });
      setShowForm(false);
      setKeywords("");
      setAlertLocation("");
      setSalaryMin("");
      loadData();
      toast({ title: "Alert created", description: "Your job alert is now active.", variant: "success" });
    } catch (e: any) {
      setError(e.message || "Failed to create alert");
    }
  };

  const updateStatus = async (matchId: string, status: string) => {
    try {
      await api.jobSync.updateMatchStatus(matchId, status);
      setMatches((prev) => prev.map((m) => (m.id === matchId ? { ...m, status: status as JobMatch["status"] } : m)));
      toast({ title: "Status updated", description: `Job marked as "${status}".`, variant: "success" });
    } catch (e: any) {
      setError(e.message || "Update failed");
    }
  };

  return (
    <div className="space-y-8 p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-500/10">
            <Search className="h-5 w-5 text-sky-600 dark:text-sky-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Job Board Sync</h1>
            <p className="text-xs text-muted-foreground">AI-scored job matches based on your profile</p>
          </div>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-2" /> New Alert
        </Button>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {/* New Alert Form */}
      {showForm && (
        <div className="rounded-2xl border p-6 space-y-4 bg-muted/30 shadow-soft-sm">
          <h2 className="text-lg font-semibold">Create Job Alert</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label htmlFor="alert-keywords" className="text-sm font-medium">Keywords (comma-separated) *</label>
              <Input id="alert-keywords" placeholder="e.g. react, typescript, senior" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label htmlFor="alert-location" className="text-sm font-medium">Location</label>
              <Input id="alert-location" placeholder="e.g. San Francisco" value={alertLocation} onChange={(e) => setAlertLocation(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label htmlFor="alert-salary" className="text-sm font-medium">Minimum Salary ($)</label>
              <Input id="alert-salary" type="number" placeholder="e.g. 100000" value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-3">
            <Button onClick={createAlert} disabled={!keywords.trim()}>Create Alert</Button>
            <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Active Alerts */}
      {alerts.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Active Alerts ({alerts.length})</h2>
          <div className="flex flex-wrap gap-3">
            {alerts.map((a) => (
              <div key={a.id} className="flex items-center gap-2 rounded-lg border px-4 py-2 text-sm">
                <Search className="h-3 w-3" />
                {a.keywords?.join(", ")}
                {a.location && <span className="text-muted-foreground">• {a.location}</span>}

              </div>
            ))}
          </div>
        </div>
      )}

      {/* Matches */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Job Matches ({matches.length})</h2>

        {loading && matches.length === 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="rounded-2xl border p-5 space-y-3 shadow-soft-sm">
                <div className="flex items-start justify-between">
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                  <Skeleton className="h-10 w-10 rounded-full" />
                </div>
                <div className="flex gap-2">
                  <Skeleton className="h-6 w-16 rounded-lg" />
                  <Skeleton className="h-6 w-20 rounded-lg" />
                </div>
                <Skeleton className="h-8 w-full" />
              </div>
            ))}
          </div>
        ) : matches.length === 0 ? (
          <div className="text-center py-16 rounded-2xl border border-dashed bg-gradient-to-b from-muted/30 to-transparent">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 mb-4">
              <Search className="h-7 w-7 text-primary" />
            </div>
            <h3 className="text-sm font-semibold">No matches yet</h3>
            <p className="mt-1 text-xs text-muted-foreground max-w-xs mx-auto">
              Create an alert to start receiving AI-scored job matches.
            </p>
            <Button className="mt-5 gap-2 rounded-xl" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4" /> Create your first alert
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {matches.map((m) => (
              <div key={m.id} className="rounded-2xl border p-5 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold text-lg">{m.title || "Untitled Position"}</h3>
                      <span className={`px-2 py-0.5 rounded-lg text-[11px] font-medium ${STATUS_COLORS[m.status || "new"] || STATUS_COLORS.new}`}>
                        {m.status || "new"}
                      </span>
                    </div>
                    {m.company && <p className="text-sm text-muted-foreground">{m.company} {m.location && `• ${m.location}`}</p>}
                    {m.match_reasons && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {(Array.isArray(m.match_reasons) ? m.match_reasons : []).map((r: string, i: number) => (
                          <span key={i} className="text-[11px] bg-muted px-2 py-0.5 rounded-lg">{r}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Score */}
                  <div className="text-center shrink-0">
                    <div className={`text-3xl font-bold ${
                      (m.match_score || 0) >= 80 ? "text-green-600 dark:text-green-400" : (m.match_score || 0) >= 60 ? "text-yellow-600 dark:text-yellow-400" : "text-red-600 dark:text-red-400"
                    }`}>
                      {m.match_score || 0}
                    </div>
                    <div className="text-xs text-muted-foreground">Match</div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 mt-4 pt-3 border-t">
                  <Button size="sm" variant="outline" onClick={() => updateStatus(m.id, "interested")}>
                    <ThumbsUp className="h-3 w-3 mr-1" /> Interested
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => updateStatus(m.id, "applied")}>
                    <Star className="h-3 w-3 mr-1" /> Applied
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => updateStatus(m.id, "rejected")} className="text-red-500 dark:text-red-400">
                    <ThumbsDown className="h-3 w-3 mr-1" /> Pass
                  </Button>
                  {m.source_url && sanitizeUrl(m.source_url) && (
                    <a href={sanitizeUrl(m.source_url)} target="_blank" rel="noopener noreferrer" className="ml-auto">
                      <Button size="sm" variant="ghost">
                        <ExternalLink className="h-3 w-3 mr-1" /> View
                      </Button>
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
