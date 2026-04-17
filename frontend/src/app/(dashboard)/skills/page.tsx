"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type {
  UserSkill,
  UserSkillGap,
  UserLearningGoal,
  SkillsProfileSummary,
  SkillCategory,
  Proficiency,
  GapSeverity,
} from "@/lib/firestore/models";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  GraduationCap,
  Plus,
  Loader2,
  Target,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Trash2,
  ChevronDown,
  Brain,
  Zap,
  BookOpen,
  X,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

/* ── Severity colors ───────────────────────────────────────────────── */

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
  high: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
  medium: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20",
  low: "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20",
};

const PROFICIENCY_COLORS: Record<string, string> = {
  beginner: "bg-slate-500/10 text-slate-600",
  intermediate: "bg-blue-500/10 text-blue-600",
  advanced: "bg-purple-500/10 text-purple-600",
  expert: "bg-amber-500/10 text-amber-600",
};

/* ── Skill Card ────────────────────────────────────────────────────── */

function SkillCard({ skill, onDelete }: { skill: UserSkill; onDelete: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-3 hover:bg-muted/50 transition-colors">
      <div className="flex items-center gap-3 min-w-0">
        <div>
          <p className="font-medium text-sm truncate">{skill.skill_name}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge variant="outline" className="text-2xs">{skill.category.replace(/_/g, " ")}</Badge>
            <Badge className={cn("text-2xs", PROFICIENCY_COLORS[skill.proficiency])}>{skill.proficiency}</Badge>
            {skill.years_experience != null && (
              <span className="text-2xs text-muted-foreground">{skill.years_experience}y</span>
            )}
          </div>
        </div>
      </div>
      <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={onDelete}>
        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
      </Button>
    </div>
  );
}

/* ── Gap Card ──────────────────────────────────────────────────────── */

function GapCard({ gap, onUpdate }: { gap: UserSkillGap; onUpdate: (status: string) => void }) {
  return (
    <div className={cn("rounded-lg border p-4", SEVERITY_COLORS[gap.gap_severity])}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <h4 className="font-semibold text-sm truncate">{gap.skill_name}</h4>
          </div>
          <div className="flex items-center gap-2 text-2xs">
            <Badge variant="outline" className="text-2xs">{gap.gap_severity}</Badge>
            <span>Priority: {gap.priority_score.toFixed(0)}</span>
            <span>Seen in {gap.frequency} app{gap.frequency !== 1 ? "s" : ""}</span>
          </div>
          {gap.current_level && gap.target_level && (
            <p className="text-2xs mt-1 opacity-80">
              {gap.current_level} → {gap.target_level}
            </p>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          {gap.status === "open" && (
            <Button size="sm" variant="outline" className="h-7 text-2xs" onClick={() => onUpdate("in_progress")}>
              Start
            </Button>
          )}
          {gap.status === "in_progress" && (
            <Button size="sm" variant="outline" className="h-7 text-2xs" onClick={() => onUpdate("closed")}>
              <CheckCircle className="h-3 w-3 mr-1" /> Close
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Goal Card ─────────────────────────────────────────────────────── */

function GoalCard({
  goal,
  onUpdate,
  onDelete,
}: {
  goal: UserLearningGoal;
  onUpdate: (data: Record<string, any>) => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl border p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="font-semibold text-sm">{goal.title}</h4>
          {goal.description && <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{goal.description}</p>}
        </div>
        <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={onDelete}>
          <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-2xs">{goal.goal_type.replace(/_/g, " ")}</Badge>
        <Badge variant={goal.status === "active" ? "default" : "secondary"} className="text-2xs">{goal.status}</Badge>
        {goal.target_date && <span className="text-2xs text-muted-foreground">Due: {new Date(goal.target_date).toLocaleDateString()}</span>}
      </div>
      {goal.target_skills?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {goal.target_skills.map((s) => (
            <Badge key={s} variant="outline" className="text-2xs font-normal">{s}</Badge>
          ))}
        </div>
      )}
      {/* eslint-disable-next-line jsx-a11y/prefer-tag-over-role */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden" role="progressbar" aria-valuenow={goal.progress_pct} aria-valuemin={0} aria-valuemax={100}>
          {/* Dynamic width requires inline style — Tailwind cannot purge dynamic values */}
          <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${goal.progress_pct}%` }} />
        </div>
        <span className="text-2xs text-muted-foreground tabular-nums">{goal.progress_pct}%</span>
      </div>
    </div>
  );
}

/* ── Add Skill Form ────────────────────────────────────────────────── */

function AddSkillForm({ onAdd }: { onAdd: (data: any) => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<SkillCategory>("technical");
  const [proficiency, setProficiency] = useState<Proficiency>("intermediate");

  const submit = () => {
    if (!name.trim()) return;
    onAdd({ skill_name: name.trim(), category, proficiency });
    setName("");
  };

  return (
    <div className="flex items-center gap-2 p-3 border rounded-lg bg-muted/30">
      <Input placeholder="Skill name" value={name} onChange={(e) => setName(e.target.value)} className="h-8 text-sm flex-1" onKeyDown={(e) => e.key === "Enter" && submit()} />
      <select title="Skill category" value={category} onChange={(e) => setCategory(e.target.value as SkillCategory)} className="h-8 rounded-md border bg-background px-2 text-xs">
        <option value="technical">Technical</option>
        <option value="soft_skill">Soft Skill</option>
        <option value="tool">Tool</option>
        <option value="language">Language</option>
        <option value="framework">Framework</option>
        <option value="methodology">Methodology</option>
        <option value="certification">Certification</option>
        <option value="domain">Domain</option>
        <option value="other">Other</option>
      </select>
      <select title="Proficiency level" value={proficiency} onChange={(e) => setProficiency(e.target.value as Proficiency)} className="h-8 rounded-md border bg-background px-2 text-xs">
        <option value="beginner">Beginner</option>
        <option value="intermediate">Intermediate</option>
        <option value="advanced">Advanced</option>
        <option value="expert">Expert</option>
      </select>
      <Button size="sm" className="h-8" onClick={submit} disabled={!name.trim()}>
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

/* ── Add Goal Form ─────────────────────────────────────────────────── */

function AddGoalForm({ onAdd }: { onAdd: (data: any) => void }) {
  const [title, setTitle] = useState("");

  const submit = () => {
    if (!title.trim()) return;
    onAdd({ title: title.trim() });
    setTitle("");
  };

  return (
    <div className="flex items-center gap-2 p-3 border rounded-lg bg-muted/30">
      <Input placeholder="New learning goal..." value={title} onChange={(e) => setTitle(e.target.value)} className="h-8 text-sm flex-1" onKeyDown={(e) => e.key === "Enter" && submit()} />
      <Button size="sm" className="h-8" onClick={submit} disabled={!title.trim()}>
        <Plus className="h-3.5 w-3.5 mr-1" /> Add Goal
      </Button>
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export default function SkillsDevelopmentPage() {
  const { session } = useAuth();
  const [skills, setSkills] = useState<UserSkill[]>([]);
  const [gaps, setGaps] = useState<UserSkillGap[]>([]);
  const [goals, setGoals] = useState<UserLearningGoal[]>([]);
  const [summary, setSummary] = useState<SkillsProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [tab, setTab] = useState<"skills" | "gaps" | "goals">("skills");

  useEffect(() => {
    if (session?.access_token) api.setToken(session.access_token);
  }, [session?.access_token]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [sk, ga, go, su] = await Promise.all([
        api.development.listSkills(),
        api.development.listGaps(),
        api.development.listGoals(),
        api.development.getSummary(),
      ]);
      setSkills(Array.isArray(sk) ? sk : []);
      setGaps(Array.isArray(ga) ? ga : []);
      setGoals(Array.isArray(go) ? go : []);
      setSummary(su);
    } catch {
      toast({ title: "Failed to load data", variant: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleAddSkill = async (data: any) => {
    try {
      await api.development.upsertSkill(data);
      await loadAll();
      toast({ title: "Skill added" });
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  const handleDeleteSkill = async (id: string) => {
    try {
      await api.development.deleteSkill(id);
      await loadAll();
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  const handleSyncGaps = async () => {
    setSyncing(true);
    try {
      const data = await api.development.syncGaps();
      setGaps(Array.isArray(data) ? data : []);
      toast({ title: "Gaps synced from all applications" });
    } catch { toast({ title: "Sync failed", variant: "error" }); }
    finally { setSyncing(false); }
  };

  const handleUpdateGap = async (gapId: string, status: string) => {
    try {
      await api.development.updateGap(gapId, { status });
      await loadAll();
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  const handleAddGoal = async (data: any) => {
    try {
      await api.development.createGoal(data);
      await loadAll();
      toast({ title: "Goal created" });
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  const handleUpdateGoal = async (goalId: string, data: Record<string, any>) => {
    try {
      await api.development.updateGoal(goalId, data);
      await loadAll();
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  const handleDeleteGoal = async (goalId: string) => {
    try {
      await api.development.deleteGoal(goalId);
      await loadAll();
    } catch { toast({ title: "Failed", variant: "error" }); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="container max-w-5xl py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <GraduationCap className="h-6 w-6 text-primary" /> Skills & Development
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Your global skill profile, gap analysis, and learning goals
        </p>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-xl border p-4 text-center">
            <Brain className="h-5 w-5 text-blue-500 mx-auto mb-1" />
            <p className="text-2xl font-bold">{summary.total_skills}</p>
            <p className="text-2xs text-muted-foreground">Skills</p>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <Target className="h-5 w-5 text-orange-500 mx-auto mb-1" />
            <p className="text-2xl font-bold">{summary.open_gaps}</p>
            <p className="text-2xs text-muted-foreground">Open Gaps</p>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <AlertTriangle className="h-5 w-5 text-red-500 mx-auto mb-1" />
            <p className="text-2xl font-bold">{summary.critical_gaps + summary.high_gaps}</p>
            <p className="text-2xs text-muted-foreground">Critical/High</p>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <Zap className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
            <p className="text-2xl font-bold">{summary.active_goals}</p>
            <p className="text-2xs text-muted-foreground">Active Goals</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b pb-0">
        {(["skills", "gaps", "goals"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "skills" ? `Skills (${skills.length})` : t === "gaps" ? `Gaps (${gaps.length})` : `Goals (${goals.length})`}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "skills" && (
        <div className="space-y-3">
          <AddSkillForm onAdd={handleAddSkill} />
          {skills.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">No skills added yet. Add your first skill above.</p>
          ) : (
            <div className="space-y-2">
              {skills.map((s) => (
                <SkillCard key={s.id} skill={s} onDelete={() => handleDeleteSkill(s.id)} />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "gaps" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Skill gaps aggregated across all your applications</p>
            <Button size="sm" variant="outline" onClick={handleSyncGaps} disabled={syncing}>
              <RefreshCw className={cn("h-3.5 w-3.5 mr-1", syncing && "animate-spin")} />
              {syncing ? "Syncing…" : "Sync from Apps"}
            </Button>
          </div>
          {gaps.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">No gaps found. Click &ldquo;Sync from Apps&rdquo; to aggregate gaps from your applications.</p>
          ) : (
            <div className="space-y-2">
              {gaps.map((g) => (
                <GapCard key={g.id} gap={g} onUpdate={(status) => handleUpdateGap(g.id, status)} />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "goals" && (
        <div className="space-y-3">
          <AddGoalForm onAdd={handleAddGoal} />
          {goals.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">No learning goals yet. Add your first goal above.</p>
          ) : (
            <div className="space-y-3">
              {goals.map((g) => (
                <GoalCard
                  key={g.id}
                  goal={g}
                  onUpdate={(data) => handleUpdateGoal(g.id, data)}
                  onDelete={() => handleDeleteGoal(g.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
