"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { LearningChallenge, LearningStreak } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  Zap, Loader2, CheckCircle, XCircle, Flame, Trophy, Star,
  RefreshCw, Brain, Target, BookOpen, Code, ArrowRight,
  TrendingUp, Award, Clock, ChevronDown,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";

const LEVEL_EMOJI = ["🌱", "🌿", "🌳", "🏆", "💎", "🔥"];

function StreakCard({ streak }: { streak: LearningStreak | null }) {
  if (!streak) return null;
  const level = Math.min(streak.level || 1, LEVEL_EMOJI.length);
  const accuracy = (streak.total_challenges || 0) > 0 ? Math.round(((streak.correct_challenges || 0) / (streak.total_challenges || 1)) * 100) : 0;

  return (
    <div className="rounded-2xl border bg-gradient-to-br from-amber-500/5 via-orange-500/5 to-transparent p-5 shadow-soft-sm">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <Flame className={cn("h-5 w-5", (streak.current_streak || 0) > 0 ? "text-orange-500" : "text-muted-foreground/30")} />
          </div>
          <p className="text-2xl font-bold tabular-nums">{streak.current_streak || 0}</p>
          <p className="text-2xs text-muted-foreground">Day Streak</p>
        </div>
        <div className="text-center">
          <Trophy className="h-5 w-5 text-amber-500 mx-auto mb-1" />
          <p className="text-2xl font-bold tabular-nums">{streak.longest_streak || 0}</p>
          <p className="text-2xs text-muted-foreground">Best Streak</p>
        </div>
        <div className="text-center">
          <Star className="h-5 w-5 text-violet-500 mx-auto mb-1" />
          <p className="text-2xl font-bold tabular-nums">{(streak.total_points || 0).toLocaleString()}</p>
          <p className="text-2xs text-muted-foreground">Points</p>
        </div>
        <div className="text-center">
          <Target className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
          <p className="text-2xl font-bold tabular-nums">{accuracy}%</p>
          <p className="text-2xs text-muted-foreground">Accuracy</p>
        </div>
        <div className="text-center">
          <span className="text-2xl block mb-1">{LEVEL_EMOJI[level - 1] || "🌱"}</span>
          <p className="text-2xl font-bold tabular-nums">Lv.{level}</p>
          <p className="text-2xs text-muted-foreground">Level</p>
        </div>
      </div>
    </div>
  );
}

export default function LearningPage() {
  const { user, session: authSession } = useAuth();
  const [streak, setStreak] = useState<LearningStreak | null>(null);
  const [profileSkills, setProfileSkills] = useState<string[]>([]);

  // Load profile skills for personalized challenges
  useEffect(() => {
    const token = authSession?.access_token;
    if (!token) return;
    api.setToken(token);
    api.profile.get().then((p: any) => {
      if (!p?.skills) return;
      setProfileSkills(p.skills.map((s: any) => typeof s === "string" ? s : s.name).filter(Boolean).slice(0, 10));
    }).catch(() => {});
  }, [authSession?.access_token]);
  const [challenges, setChallenges] = useState<LearningChallenge[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [freeformAnswer, setFreeformAnswer] = useState("");
  const [answerResult, setAnswerResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [s, t] = await Promise.all([api.learning.getStreak(), api.learning.getToday()]);
      setStreak(s || { current_streak: 0, longest_streak: 0, total_points: 0, total_challenges: 0, correct_challenges: 0, level: 1 });
      setChallenges(t?.challenges || t || []);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const generateChallenges = async () => {
    setGenerating(true);
    setError("");
    try {
      const result = await api.learning.generate(profileSkills.length > 0 ? { skills: profileSkills } : undefined);
      setChallenges(result?.challenges || result || []);
      setCurrentIdx(0);
      setAnswerResult(null);
      setSelectedAnswer(null);
      toast({ title: "Challenges generated!" });
    } catch (e: any) { setError(e.message); }
    finally { setGenerating(false); }
  };

  const submitAnswer = async () => {
    const challenge = challenges[currentIdx];
    if (!challenge) return;
    const ans = challenge.type === "freeform" ? freeformAnswer : selectedAnswer;
    if (!ans) return;
    setSubmitting(true);
    try {
      const result = await api.learning.submitAnswer(challenge.id, ans);
      setAnswerResult(result);
      // Update streak
      const s = await api.learning.getStreak();
      if (s) setStreak(s);
    } catch (e: any) { setError(e.message); }
    finally { setSubmitting(false); }
  };

  const nextChallenge = () => {
    if (currentIdx < challenges.length - 1) {
      setCurrentIdx((i) => i + 1);
      setAnswerResult(null);
      setSelectedAnswer(null);
      setFreeformAnswer("");
    }
  };

  const challenge = challenges[currentIdx];
  const allDone = challenges.length > 0 && currentIdx >= challenges.length - 1 && answerResult;

  const challengeTypeConfig: Record<string, { icon: any; color: string; label: string }> = {
    quiz: { icon: Brain, color: "bg-blue-500/10 text-blue-500", label: "Quiz" },
    scenario: { icon: Code, color: "bg-violet-500/10 text-violet-500", label: "Scenario" },
    freeform: { icon: BookOpen, color: "bg-emerald-500/10 text-emerald-500", label: "Open-Ended" },
    flashcard: { icon: Zap, color: "bg-amber-500/10 text-amber-500", label: "Flashcard" },
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-glow-sm">
          <BookOpen className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Skill Lab</h1>
          <p className="text-sm text-muted-foreground">Daily AI-powered challenges to sharpen your career skills</p>
        </div>
      </div>

      {/* Streak card */}
      <StreakCard streak={streak} />

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      {/* Loading */}
      {loading && (
        <div className="rounded-2xl border bg-card p-10 text-center">
          <Loader2 className="h-8 w-8 text-primary animate-spin mx-auto" />
          <p className="text-sm text-muted-foreground mt-3">Loading your challenges...</p>
        </div>
      )}

      {/* No challenges — generate */}
      {!loading && challenges.length === 0 && (
        <div className="rounded-2xl border border-dashed bg-gradient-to-br from-violet-500/5 to-transparent p-10 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-500/10 mx-auto mb-4">
            <Brain className="h-7 w-7 text-violet-500" />
          </div>
          <h3 className="font-semibold">Ready for today&apos;s challenges?</h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">AI generates personalized challenges based on your skill gaps and career goals.</p>
          <Button className="mt-4 rounded-xl gap-2" onClick={generateChallenges} disabled={generating}>
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            {generating ? "Generating..." : "Generate Today's Challenges"}
          </Button>
        </div>
      )}

      {/* Active challenge */}
      {!loading && challenge && !allDone && (
        <div className="space-y-4">
          {/* Progress */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-500 transition-all" style={{ width: `${((currentIdx + 1) / challenges.length) * 100}%` }} />
            </div>
            <span className="text-xs text-muted-foreground font-mono">{currentIdx + 1}/{challenges.length}</span>
          </div>

          {/* Question card */}
          <div className="rounded-2xl border bg-card p-6 shadow-soft-sm space-y-4">
            <div className="flex items-center gap-2">
              {(() => {
                const cfg = challengeTypeConfig[challenge.type] || challengeTypeConfig.quiz;
                return <Badge variant="outline" className={cn("text-[10px] gap-1", cfg.color)}><cfg.icon className="h-3 w-3" /> {cfg.label}</Badge>;
              })()}
              {challenge.skill && <Badge variant="secondary" className="text-[10px]">{challenge.skill}</Badge>}
              {challenge.difficulty && <Badge variant="outline" className="text-[10px] capitalize">{challenge.difficulty}</Badge>}
            </div>

            <p className="text-base font-medium leading-relaxed">{challenge.question || challenge.text}</p>

            {/* Multiple choice */}
            {challenge.options && challenge.options.length > 0 && !answerResult && (
              <div className="space-y-2">
                {challenge.options.map((opt: string, i: number) => (
                  <button key={i} onClick={() => setSelectedAnswer(opt)}
                    className={cn("w-full text-left rounded-xl border p-3 text-sm transition-all",
                      selectedAnswer === opt ? "border-primary bg-primary/5 font-medium" : "border-border hover:border-primary/30 hover:bg-muted/30"
                    )}>
                    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-muted text-2xs font-bold mr-2">{String.fromCharCode(65 + i)}</span>
                    {opt}
                  </button>
                ))}
              </div>
            )}

            {/* Freeform */}
            {(challenge.type === "freeform" || challenge.type === "scenario") && !challenge.options?.length && !answerResult && (
              <Textarea className="h-28 resize-none rounded-xl text-sm" placeholder="Type your answer..." value={freeformAnswer} onChange={(e) => setFreeformAnswer(e.target.value)} maxLength={2000} />
            )}

            {/* Answer feedback */}
            {answerResult && (
              <div className={cn("rounded-xl p-4 space-y-2 animate-fade-up", answerResult.correct ? "bg-emerald-500/10 border border-emerald-500/20" : "bg-rose-500/10 border border-rose-500/20")}>
                <div className="flex items-center gap-2">
                  {answerResult.correct ? <CheckCircle className="h-5 w-5 text-emerald-500" /> : <XCircle className="h-5 w-5 text-rose-500" />}
                  <span className="font-semibold text-sm">{answerResult.correct ? "Correct!" : "Not quite"}</span>
                  {answerResult.points > 0 && <Badge variant="secondary" className="text-[10px] ml-auto">+{answerResult.points} pts</Badge>}
                </div>
                {answerResult.explanation && <p className="text-xs text-muted-foreground">{answerResult.explanation}</p>}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2">
              {!answerResult ? (
                <Button onClick={submitAnswer} disabled={submitting || (!selectedAnswer && !freeformAnswer.trim())} className="rounded-xl gap-2">
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                  Submit Answer
                </Button>
              ) : currentIdx < challenges.length - 1 ? (
                <Button onClick={nextChallenge} className="rounded-xl gap-2">
                  Next Challenge <ArrowRight className="h-4 w-4" />
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* All done */}
      {allDone && (
        <div className="rounded-2xl border bg-gradient-to-br from-emerald-500/5 via-teal-500/5 to-transparent p-8 text-center shadow-soft-sm">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 mx-auto mb-4">
            <Trophy className="h-8 w-8 text-emerald-500" />
          </div>
          <h2 className="text-xl font-bold">All Done for Today!</h2>
          <p className="text-sm text-muted-foreground mt-1">Come back tomorrow to keep your streak going.</p>
          <div className="flex justify-center gap-3 mt-4">
            <Button variant="outline" className="rounded-xl gap-2" onClick={generateChallenges} disabled={generating}>
              <RefreshCw className={cn("h-4 w-4", generating && "animate-spin")} /> More Challenges
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
