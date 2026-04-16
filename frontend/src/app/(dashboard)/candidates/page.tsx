"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  Users, Plus, Loader2, Search, Mail, MapPin,
  Building2, X, UserPlus, LayoutGrid, List,
} from "lucide-react";
import { RoleGate } from "@/components/role-gate";
import { toast } from "@/hooks/use-toast";

const STAGES = [
  { key: "sourced", label: "Sourced", color: "bg-blue-500", lightColor: "bg-blue-500/10 border-blue-500/20" },
  { key: "screened", label: "Screened", color: "bg-cyan-500", lightColor: "bg-cyan-500/10 border-cyan-500/20" },
  { key: "submitted", label: "Submitted", color: "bg-violet-500", lightColor: "bg-violet-500/10 border-violet-500/20" },
  { key: "interviewing", label: "Interviewing", color: "bg-amber-500", lightColor: "bg-amber-500/10 border-amber-500/20" },
  { key: "offered", label: "Offered", color: "bg-emerald-500", lightColor: "bg-emerald-500/10 border-emerald-500/20" },
  { key: "placed", label: "Placed", color: "bg-green-600", lightColor: "bg-green-600/10 border-green-600/20" },
];

export default function CandidatesPage() {
  const { session } = useAuth();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"kanban" | "list">("kanban");

  // Add form
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [newClient, setNewClient] = useState("");
  const [newNotes, setNewNotes] = useState("");

  useEffect(() => {
    if (session?.access_token) {
      api.setToken(session.access_token);
      loadData();
    }
  }, [session?.access_token]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([
        api.request("/candidates"),
        api.request("/candidates/stats"),
      ]);
      setCandidates(Array.isArray(c) ? c : []);
      setStats(s || {});
    } catch (e: any) {
      toast({ title: "Failed to load candidates", description: e.message, variant: "error" });
    } finally { setLoading(false); }
  };

  const addCandidate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.request("/candidates", {
        method: "POST",
        body: { name: newName, email: newEmail || undefined, phone: newPhone || undefined, location: newLocation || undefined, client_company: newClient || undefined, notes: newNotes || undefined },
      });
      setShowAdd(false);
      setNewName(""); setNewEmail(""); setNewPhone(""); setNewLocation(""); setNewClient(""); setNewNotes("");
      await loadData();
      toast({ title: "Candidate added!" });
    } catch (e: any) { toast({ title: "Failed", description: e.message }); }
    setCreating(false);
  };

  const moveCandidate = async (id: string, stage: string) => {
    try {
      await api.request(`/candidates/${id}/move`, { method: "POST", body: { stage } });
      setCandidates((prev) => prev.map((c) => c.id === id ? { ...c, pipeline_stage: stage } : c));
      toast({ title: `Moved to ${stage}` });
    } catch (e: any) {
      toast({ title: "Failed to move candidate", description: e.message, variant: "error" });
    }
  };

  const filtered = candidates.filter((c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (c.name || "").toLowerCase().includes(q) || (c.email || "").toLowerCase().includes(q) || (c.client_company || "").toLowerCase().includes(q);
  });

  return (
    <RoleGate feature="pipeline" title="Candidate Pipeline" features={["Track candidates across stages", "Manage hiring pipeline", "Team collaboration on candidates"]}>
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-glow-sm">
            <Users className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Candidate Pipeline</h1>
            <p className="text-sm text-muted-foreground">{stats.total || 0} candidates · {stats.placed || 0} placed</p>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 rounded-xl h-9 w-48 text-sm" />
          </div>
          <div className="flex rounded-xl border overflow-hidden">
            <button onClick={() => setView("kanban")} className={cn("px-2.5 h-9 flex items-center transition-colors", view === "kanban" ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => setView("list")} className={cn("px-2.5 h-9 flex items-center border-l transition-colors", view === "list" ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>
              <List className="h-3.5 w-3.5" />
            </button>
          </div>
          <Button onClick={() => setShowAdd(true)} className="rounded-xl gap-1.5">
            <UserPlus className="h-4 w-4" /> Add Candidate
          </Button>
        </div>
      </div>

      {/* Stats row */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {STAGES.map((stage) => (
          <div key={stage.key} className={cn("rounded-lg border px-3 py-1.5 text-center min-w-[100px] transition-all duration-200 hover:shadow-soft-sm", stage.lightColor)}>
            <p className="text-lg font-bold tabular-nums">{stats[stage.key] || 0}</p>
            <p className="text-[10px] text-muted-foreground">{stage.label}</p>
          </div>
        ))}
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="rounded-2xl border bg-card p-5 shadow-soft-sm space-y-3 animate-fade-up">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Add Candidate</h2>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowAdd(false)}><X className="h-4 w-4" /></Button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Input placeholder="Full name *" value={newName} onChange={(e) => setNewName(e.target.value)} className="rounded-xl" />
            <Input placeholder="Email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="rounded-xl" />
            <Input placeholder="Phone" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} className="rounded-xl" />
            <Input placeholder="Location" value={newLocation} onChange={(e) => setNewLocation(e.target.value)} className="rounded-xl" />
            <Input placeholder="Client company" value={newClient} onChange={(e) => setNewClient(e.target.value)} className="rounded-xl" />
          </div>
          <Textarea placeholder="Notes..." value={newNotes} onChange={(e) => setNewNotes(e.target.value)} className="rounded-xl h-16 resize-none" />
          <Button onClick={addCandidate} disabled={creating || !newName.trim()} className="rounded-xl gap-1">
            {creating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} Add
          </Button>
        </div>
      )}

      {/* Kanban / List Board */}
      {loading ? (
        <div className="text-center py-12"><Loader2 className="h-8 w-8 animate-spin mx-auto text-muted-foreground" /></div>
      ) : filtered.length === 0 && !search ? (
        <div className="rounded-2xl border border-dashed bg-card/50 p-10 text-center">
          <Users className="h-10 w-10 text-muted-foreground/20 mx-auto mb-3" />
          <h3 className="font-semibold text-sm">No candidates yet</h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">Add candidates to track them through your recruitment pipeline.</p>
          <Button className="mt-4 rounded-xl gap-2" onClick={() => setShowAdd(true)}><UserPlus className="h-4 w-4" /> Add First Candidate</Button>
        </div>
      ) : view === "list" ? (
        /* ── List View ── */
        <div className="rounded-2xl border bg-card overflow-hidden shadow-soft-sm">
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-0 border-b px-4 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            <span>Candidate</span>
            <span>Stage</span>
            <span>Company</span>
            <span>Location</span>
          </div>
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">No candidates match your search.</div>
          ) : (
            filtered.map((c) => {
              const stage = STAGES.find((s) => s.key === c.pipeline_stage);
              return (
                <div key={c.id} className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-0 items-center px-4 py-3 border-b last:border-b-0 hover:bg-muted/30 transition-colors group">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{c.name}</p>
                    {c.email && <p className="text-[10px] text-muted-foreground flex items-center gap-0.5"><Mail className="h-2.5 w-2.5" /> {c.email}</p>}
                  </div>
                  <div>
                    {stage ? (
                      <span className={cn("inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border", stage.lightColor)}>
                        <span className={cn("h-1.5 w-1.5 rounded-full", stage.color)} />
                        {stage.label}
                      </span>
                    ) : (
                      <span className="text-[10px] text-muted-foreground">—</span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {c.client_company ? <span className="flex items-center gap-0.5"><Building2 className="h-2.5 w-2.5" /> {c.client_company}</span> : "—"}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {c.location ? <span className="flex items-center gap-0.5"><MapPin className="h-2.5 w-2.5" /> {c.location}</span> : "—"}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        /* ── Kanban View ── */
        <div className="flex gap-3 overflow-x-auto pb-4">
          {STAGES.map((stage) => {
            const stageCards = filtered.filter((c) => c.pipeline_stage === stage.key);
            return (
              <div key={stage.key} className="min-w-[240px] w-[240px] shrink-0">
                {/* Column header */}
                <div className="flex items-center gap-2 mb-2 px-1">
                  <div className={cn("h-2 w-2 rounded-full", stage.color)} />
                  <span className="text-xs font-semibold">{stage.label}</span>
                  <Badge variant="secondary" className="text-[9px] ml-auto">{stageCards.length}</Badge>
                </div>

                {/* Cards */}
                <div className="space-y-2">
                  {stageCards.map((c) => (
                    <div key={c.id} className="rounded-xl border bg-card p-3 shadow-soft-sm hover:shadow-soft-md hover:-translate-y-0.5 transition-all duration-300 group">
                      <div className="flex items-start justify-between gap-1">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold truncate">{c.name}</p>
                          {c.client_company && <p className="text-[10px] text-muted-foreground flex items-center gap-0.5"><Building2 className="h-2.5 w-2.5" /> {c.client_company}</p>}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {c.email && <span className="text-[9px] text-muted-foreground flex items-center gap-0.5"><Mail className="h-2 w-2" /> {c.email.split("@")[0]}</span>}
                        {c.location && <span className="text-[9px] text-muted-foreground flex items-center gap-0.5"><MapPin className="h-2 w-2" /> {c.location}</span>}
                      </div>
                      {c.tags?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {c.tags.slice(0, 3).map((t: string, i: number) => (
                            <span key={i} className="text-[8px] bg-muted px-1.5 py-0.5 rounded">{t}</span>
                          ))}
                        </div>
                      )}
                      {/* Move buttons */}
                      <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        {STAGES.filter((s) => s.key !== stage.key).slice(0, 3).map((s) => (
                          <button key={s.key} onClick={() => moveCandidate(c.id, s.key)}
                            className={cn("text-[8px] px-1.5 py-0.5 rounded border transition-colors hover:bg-muted", s.lightColor)}>
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {stageCards.length === 0 && (
                    <div className="rounded-xl border border-dashed bg-muted/20 p-4 text-center">
                      <p className="text-[10px] text-muted-foreground">No candidates</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
    </RoleGate>
  );
}
