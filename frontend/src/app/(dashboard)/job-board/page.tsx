"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { JobAlert, JobMatch } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { sanitizeUrl } from "@/lib/sanitize";
import { toast } from "@/hooks/use-toast";
import {
  Search, Loader2, Plus, ExternalLink, Star, ThumbsUp, ThumbsDown,
  Briefcase, MapPin, DollarSign, TrendingUp, Zap, ArrowRight,
  Target, Clock, Building2, ChevronDown,
} from "lucide-react";

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  new: { color: "bg-blue-500/10 text-blue-500 border-blue-500/20", label: "New" },
  interested: { color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20", label: "Interested" },
  applied: { color: "bg-violet-500/10 text-violet-500 border-violet-500/20", label: "Applied" },
  rejected: { color: "bg-rose-500/10 text-rose-500 border-rose-500/20", label: "Passed" },
  saved: { color: "bg-amber-500/10 text-amber-500 border-amber-500/20", label: "Saved" },
};

function MatchGauge({ value }: { value: number }) {
  const color = value >= 80 ? "text-emerald-500" : value >= 60 ? "text-amber-500" : "text-rose-500";
  const bg = value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={cn("text-2xl font-bold tabular-nums", color)}>{value}%</div>
      <div className="w-12 h-1 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full", bg)} style={{ width: `${value}%` }} />
      </div>
      <span className="text-[9px] text-muted-foreground uppercase">Match</span>
    </div>
  );
}

export default function JobBoardPage() {
  const router = useRouter();
  const { user, session: authSession } = useAuth();

  const [alerts, setAlerts] = useState<JobAlert[]>([]);
  const [matches, setMatches] = useState<JobMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Alert form
  const [showForm, setShowForm] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [alertLocation, setAlertLocation] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [creating, setCreating] = useState(false);

  // Set token and load data only when auth is ready
  useEffect(() => {
    if (authSession?.access_token) {
      api.setToken(authSession.access_token);
      loadData();
    }
  }, [authSession?.access_token]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [a, m] = await Promise.all([api.jobSync.getAlerts(), api.jobSync.getMatches()]);
      setAlerts(a || []);
      setMatches(m || []);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const createAlert = async () => {
    if (!keywords.trim()) return;
    setCreating(true);
    try {
      await api.jobSync.createAlert({ keywords: keywords.split(",").map((k) => k.trim()), location: alertLocation || undefined, min_salary: salaryMin ? parseInt(salaryMin) : undefined });
      setShowForm(false); setKeywords(""); setAlertLocation(""); setSalaryMin("");
      loadData();
      toast({ title: "Alert created" });
    } catch (e: any) { setError(e.message); }
    finally { setCreating(false); }
  };

  const updateStatus = async (id: string, status: string) => {
    try {
      await api.jobSync.updateMatchStatus(id, status);
      setMatches((prev) => prev.map((m) => m.id === id ? { ...m, status: status as any } : m));
    } catch (e: any) {
      toast({ title: "Failed to update status", description: e.message, variant: "error" });
    }
  };

  const applyToJob = (match: JobMatch) => {
    // Pre-fill the application wizard with this job's data
    const params = new URLSearchParams();
    if (match.title) params.set("jobTitle", match.title);
    if (match.company) params.set("company", match.company);
    if (match.description) params.set("jdText", match.description.slice(0, 2000));
    router.push(`/new?${params.toString()}`);
  };

  const filtered = matches.filter((m) => {
    if (filter !== "all" && m.status !== filter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (m.title || "").toLowerCase().includes(q) || (m.company || "").toLowerCase().includes(q);
    }
    return true;
  });

  const stats = {
    total: matches.length,
    new: matches.filter((m) => m.status === "new").length,
    applied: matches.filter((m) => m.status === "applied").length,
    avgMatch: matches.length ? Math.round(matches.reduce((s, m) => s + (m.match_score || 0), 0) / matches.length) : 0,
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 to-blue-600 shadow-glow-sm">
            <Briefcase className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Job Intelligence</h1>
            <p className="text-sm text-muted-foreground">AI-matched opportunities with smart scoring</p>
          </div>
        </div>
        <Button onClick={() => setShowForm(!showForm)} className="rounded-xl gap-2">
          <Plus className="h-4 w-4" /> New Alert
        </Button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { icon: Briefcase, label: "Total Jobs", value: stats.total, color: "text-blue-500 bg-blue-500/10" },
          { icon: Zap, label: "New", value: stats.new, color: "text-amber-500 bg-amber-500/10" },
          { icon: Star, label: "Applied", value: stats.applied, color: "text-violet-500 bg-violet-500/10" },
          { icon: Target, label: "Avg Match", value: `${stats.avgMatch}%`, color: "text-emerald-500 bg-emerald-500/10" },
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

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      {/* Alert form */}
      {showForm && (
        <div className="rounded-2xl border bg-card p-5 shadow-soft-sm space-y-4 animate-fade-up">
          <h2 className="font-semibold">Create Job Alert</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1"><label className="text-2xs font-medium">Keywords *</label><Input placeholder="react, typescript, senior" value={keywords} onChange={(e) => setKeywords(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
            <div className="space-y-1"><label className="text-2xs font-medium">Location</label><Input placeholder="London, UK" value={alertLocation} onChange={(e) => setAlertLocation(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
            <div className="space-y-1"><label className="text-2xs font-medium">Min Salary</label><Input type="number" placeholder="80000" value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
          </div>
          <div className="flex gap-2">
            <Button onClick={createAlert} disabled={creating || !keywords.trim()} className="rounded-xl gap-2">
              {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} Create
            </Button>
            <Button variant="outline" onClick={() => setShowForm(false)} className="rounded-xl">Cancel</Button>
          </div>
        </div>
      )}

      {/* Active alerts */}
      {alerts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {alerts.map((a) => (
            <div key={a.id} className="flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-xs">
              <Search className="h-3 w-3 text-muted-foreground" />
              <span className="font-medium">{a.keywords?.join(", ")}</span>
              {a.location && <span className="text-muted-foreground flex items-center gap-0.5"><MapPin className="h-2.5 w-2.5" /> {a.location}</span>}
              <Badge variant="secondary" className="text-[9px]">Active</Badge>
            </div>
          ))}
        </div>
      )}

      {/* Filter + Search */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1 rounded-lg bg-muted/50 p-0.5">
          {["all", "new", "interested", "applied", "saved"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={cn("rounded-lg px-3 py-1.5 text-xs font-medium transition-colors capitalize", filter === f ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}>{f}</button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input placeholder="Search jobs..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-9 rounded-xl h-8 text-sm" />
        </div>
      </div>

      {/* Job listings */}
      {loading ? (
        <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40 rounded-2xl" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
          <Briefcase className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
          <h3 className="font-semibold text-sm">No job matches yet</h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">Create a job alert and we&apos;ll find AI-scored matches based on your profile.</p>
          <Button className="mt-4 rounded-xl gap-2" onClick={() => setShowForm(true)}><Plus className="h-3 w-3" /> Create Alert</Button>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {filtered.map((m) => {
            const sc = STATUS_CONFIG[m.status || "new"] || STATUS_CONFIG.new;
            return (
              <div key={m.id} className="rounded-2xl border bg-card p-4 shadow-soft-sm hover:shadow-soft-md hover:border-primary/20 transition-all group">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-sm truncate group-hover:text-primary transition-colors">{m.title || "Untitled"}</h3>
                      <Badge variant="outline" className={cn("text-[9px] border shrink-0", sc.color)}>{sc.label}</Badge>
                    </div>
                    <div className="flex items-center gap-3 text-2xs text-muted-foreground">
                      {m.company && <span className="flex items-center gap-0.5"><Building2 className="h-2.5 w-2.5" /> {m.company}</span>}
                      {m.location && <span className="flex items-center gap-0.5"><MapPin className="h-2.5 w-2.5" /> {m.location}</span>}
                      {m.salary_range && <span className="flex items-center gap-0.5"><DollarSign className="h-2.5 w-2.5" /> {m.salary_range}</span>}
                    </div>
                    {m.match_reasons && Array.isArray(m.match_reasons) && m.match_reasons.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {m.match_reasons.slice(0, 3).map((r: string, i: number) => (
                          <span key={i} className="text-[9px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 rounded">{r}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <MatchGauge value={m.match_score || 0} />
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 mt-3 pt-3 border-t">
                  <Button size="sm" variant="default" className="h-7 text-2xs rounded-lg gap-1" onClick={() => applyToJob(m)}>
                    <ArrowRight className="h-3 w-3" /> Apply
                  </Button>
                  <Button size="sm" variant="outline" className="h-7 text-2xs rounded-lg gap-1" onClick={() => updateStatus(m.id, "interested")}>
                    <ThumbsUp className="h-3 w-3" />
                  </Button>
                  <Button size="sm" variant="outline" className="h-7 text-2xs rounded-lg gap-1" onClick={() => updateStatus(m.id, "saved")}>
                    <Star className="h-3 w-3" />
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 text-2xs rounded-lg gap-1 text-muted-foreground" onClick={() => updateStatus(m.id, "rejected")}>
                    <ThumbsDown className="h-3 w-3" />
                  </Button>
                  {m.source_url && sanitizeUrl(m.source_url) && (
                    <a href={sanitizeUrl(m.source_url)} target="_blank" rel="noopener noreferrer" className="ml-auto">
                      <Button size="sm" variant="ghost" className="h-7 text-2xs rounded-lg gap-1"><ExternalLink className="h-3 w-3" /> View</Button>
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
