"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers";
import { toast } from "@/hooks/use-toast";
import api from "@/lib/api";
import type { InterviewSession, InterviewQuestion, InterviewAnswer } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  Mic, Play, Send, CheckCircle, Clock, Loader2, RotateCcw,
  Timer, Brain, Target, Zap, AlertTriangle, Trophy,
  MessageSquare, Code, Users, Briefcase, ChevronDown, Info,
} from "lucide-react";
import { AITrace } from "@/components/ui/ai-trace";
import { ScoreExplanation } from "@/components/ui/score-explanation";

/* ── Animation variants ───────────────────────────────────────── */

const fadeUp: any = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.1, duration: 0.5, ease: "easeOut" } }),
};

const staggerContainer: any = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const staggerItem: any = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: "easeOut" } },
};

const cardHover: any = {
  rest: { scale: 1, y: 0 },
  hover: { scale: 1.02, y: -2, transition: { duration: 0.2, ease: "easeOut" } },
};

type Phase = "setup" | "active" | "review";
type InterviewMode = "practice" | "timed" | "mock";

const INTERVIEW_TYPES = [
  { value: "behavioral", label: "Behavioral", icon: Users, desc: "STAR method, leadership, teamwork" },
  { value: "technical", label: "Technical", icon: Code, desc: "System design, coding, architecture" },
  { value: "situational", label: "Situational", icon: AlertTriangle, desc: "Problem-solving scenarios" },
  { value: "case", label: "Case Study", icon: Briefcase, desc: "Business analysis, strategy" },
  { value: "mixed", label: "Mixed", icon: Brain, desc: "All question types combined" },
];

const MODES = [
  { value: "practice" as InterviewMode, label: "Practice", icon: MessageSquare, desc: "Answer at your own pace", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
  { value: "timed" as InterviewMode, label: "Timed", icon: Timer, desc: "90s per question", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  { value: "mock" as InterviewMode, label: "Live Mock", icon: Mic, desc: "AI interviewer with follow-ups", color: "bg-rose-500/10 text-rose-500 border-rose-500/20" },
];

function ScoreRing({ value, size = 80, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 8) / 2, circ = 2 * Math.PI * r, offset = circ - (value / 100) * circ;
  const color = value >= 80 ? "stroke-emerald-500" : value >= 60 ? "stroke-amber-500" : "stroke-rose-500";
  return (
    <motion.div
      className="flex flex-col items-center gap-1"
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size/2} cy={size/2} r={r} strokeWidth={6} fill="none" className="stroke-muted/20" />
          <motion.circle cx={size/2} cy={size/2} r={r} strokeWidth={6} fill="none" strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: "easeOut", delay: 0.3 }}
            className={color} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-lg font-bold tabular-nums", value >= 80 ? "text-emerald-500" : value >= 60 ? "text-amber-500" : "text-rose-500")}>{value}</span>
        </div>
      </div>
      {label && <span className="text-2xs text-muted-foreground">{label}</span>}
    </motion.div>
  );
}

/* ── Timer ring for timed mode ─────────────────────────────────── */

function TimerRing({ timeLeft, total = 90, size = 48 }: { timeLeft: number; total?: number; size?: number }) {
  const r = (size - 6) / 2, circ = 2 * Math.PI * r;
  const progress = timeLeft / total;
  const offset = circ - progress * circ;
  const color = timeLeft <= 15 ? "stroke-rose-500" : timeLeft <= 30 ? "stroke-amber-500" : "stroke-primary";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={r} strokeWidth={4} fill="none" className="stroke-muted/20" />
        <motion.circle cx={size/2} cy={size/2} r={r} strokeWidth={4} fill="none" strokeLinecap="round"
          strokeDasharray={circ}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.5, ease: "linear" }}
          className={color} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={cn("text-[10px] font-bold tabular-nums", timeLeft <= 15 ? "text-rose-500" : timeLeft <= 30 ? "text-amber-500" : "text-foreground")}>
          {Math.floor(timeLeft / 60)}:{String(timeLeft % 60).padStart(2, "0")}
        </span>
      </div>
    </div>
  );
}

export default function InterviewSimulatorPage() {
  const { user, session: authSession } = useAuth();
  const searchParams = useSearchParams();
  const appId = searchParams.get("appId");
  const [phase, setPhase] = useState<Phase>("setup");
  const [mode, setMode] = useState<InterviewMode>("practice");

  // Profile data for personalization
  const [profileSummary, setProfileSummary] = useState("");
  const [profileSkills, setProfileSkills] = useState("");

  // Load profile on mount for personalization
  useEffect(() => {
    const token = authSession?.access_token;
    if (!token) return;
    api.setToken(token);
    api.profile.get().then((p: any) => {
      if (!p) return;
      const skills = (p.skills || []).map((s: any) => typeof s === "string" ? s : s.name).join(", ");
      setProfileSkills(skills);
      setProfileSummary(`${p.title || ""} with skills: ${skills.slice(0, 300)}`);
      setJobTitle(prev => p.title && !prev ? p.title : prev);
    }).catch((e) => console.error("Failed to load profile for interview", e));
  }, [authSession?.access_token]);

  // Load application context if appId is provided (e.g. from workspace "Practice Interview" link)
  useEffect(() => {
    if (!appId || !user?.id) return;

    import("@/lib/supabase").then(({ supabase }) => {
      (async () => {
        try {
          const { data: app } = await supabase
            .from("applications")
            .select("title, confirmed_facts, gaps, benchmark")
            .eq("id", appId)
            .eq("user_id", user.id)
            .maybeSingle();
          if (!app) return;
          // Auto-fill job title from application
          if (app.title) setJobTitle(prev => prev || app.title);
          // Build richer profile summary from application gap analysis
          const gapData = app.gaps || {};
          const strengths = (gapData.strengths || []).slice(0, 10).join(", ");
          const missingKeywords = (gapData.missingKeywords || []).slice(0, 10).join(", ");
          if (strengths) {
            setProfileSkills(prev => prev || strengths);
            setProfileSummary(prev =>
              prev || `Strengths: ${strengths}. Areas to improve: ${missingKeywords}`
            );
          }
        } catch (e) {
          console.warn("[Interview] Failed to load app context:", e);
        }
      })();
    });
  }, [appId, user?.id]);

  // Setup
  const [jobTitle, setJobTitle] = useState("");
  const [interviewType, setInterviewType] = useState("behavioral");
  const [difficulty, setDifficulty] = useState("intermediate");
  const [questionCount, setQuestionCount] = useState(5);

  // Session
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [answers, setAnswers] = useState<InterviewAnswer[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);

  // Timed mode
  const [timeLeft, setTimeLeft] = useState(90);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Elapsed timer
  useEffect(() => {
    if (phase !== "active") return;
    setElapsed(0);
    const interval = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(interval);
  }, [phase, currentIdx]);

  // Timed mode countdown
  useEffect(() => {
    if (phase !== "active" || mode !== "timed") return;
    setTimeLeft(90);
    timerRef.current = setInterval(() => {
      setTimeLeft((t) => {
        if (t <= 1) {
          // Auto-submit when time runs out
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return t - 1;
      });
    }, 1000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [phase, mode, currentIdx]);

  // Auto-submit on time out
  useEffect(() => {
    if (timeLeft === 0 && mode === "timed" && phase === "active" && !submittingRef.current) {
      toast({ title: "Time's up!", description: "Your answer has been submitted automatically.", variant: "warning" });
      submitAnswer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeft]);

  const startSession = async () => {
    if (!jobTitle.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.interview.start({
        job_title: jobTitle,
        interview_type: interviewType,
        difficulty,
        question_count: questionCount,
        profile_summary: profileSummary || undefined,
        skills_summary: profileSkills || undefined,
      });
      setSession(result.session);
      setQuestions(result.questions);
      setCurrentIdx(0);
      setAnswers([]);
      setPhase("active");
      toast({ title: "Interview started", description: `${result.questions.length} questions ready` });
    } catch (e: any) {
      setError(e.message || "Failed to start");
    } finally {
      setLoading(false);
    }
  };

  const submitAnswer = async () => {
    if (!session) return;
    const answerText = answer.trim() || "(No answer provided — time ran out)";
    setSubmitting(true);    submittingRef.current = true;    try {
      const result = await api.interview.submitAnswer(session.id, {
        question_id: questions[currentIdx]?.id ?? String(currentIdx),
        answer: answerText,
      });
      setAnswers((prev) => [...prev, result]);
      setAnswer("");
      if (currentIdx < questions.length - 1) {
        setCurrentIdx((prev) => prev + 1);
      } else {
        const completed = await api.interview.complete(session.id);
        setSession(completed);
        setPhase("review");
      }
    } catch (e: any) {
      setError(e.message || "Submit failed");
    } finally {
      setSubmitting(false);
      submittingRef.current = false;
    }
  };

  const restart = () => {
    setPhase("setup");
    setSession(null);
    setQuestions([]);
    setAnswers([]);
    setCurrentIdx(0);
    setAnswer("");
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const lastAnswer = answers.length > 0 ? answers[answers.length - 1] : null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <motion.div className="flex items-center gap-4" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-pink-600 shadow-glow-sm">
          <Mic className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Interview Simulator</h1>
          <p className="text-sm text-muted-foreground">AI-powered mock interviews with STAR feedback and real-time coaching</p>
        </div>
      </motion.div>

      {error && <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</motion.div>}

      {/* ── Setup Phase ─────────────────────────────────────── */}
      <AnimatePresence mode="wait">
      {phase === "setup" && (
        <motion.div key="setup" className="space-y-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} transition={{ duration: 0.4 }}>
          {/* Interview Mode Selection */}
          <div>
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Interview Mode</h2>
            <div className="grid grid-cols-3 gap-3">
              {MODES.map((m, idx) => (
                <motion.button key={m.value} onClick={() => setMode(m.value)}
                  variants={cardHover} initial="rest" whileHover="hover"
                  custom={idx}
                  className={cn("rounded-xl border p-4 text-left transition-colors",
                    mode === m.value ? "border-primary bg-primary/5 shadow-soft-sm" : "border-border hover:border-primary/30"
                  )}>
                  <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg border mb-2", m.color)}>
                    <m.icon className="h-4 w-4" />
                  </div>
                  <p className="font-semibold text-sm">{m.label}</p>
                  <p className="text-2xs text-muted-foreground mt-0.5">{m.desc}</p>
                </motion.button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2 flex items-start gap-1.5">
              <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              {mode === "practice" && "Answer each question at your own pace — no time pressure. Great for preparation."}
              {mode === "timed" && "90 seconds per question. If time runs out, your answer is auto-submitted. Simulates real interview pressure."}
              {mode === "mock" && "A simulated live interview with AI follow-up questions based on your answers."}
            </p>
          </div>

          {/* Configuration */}
          <motion.div className="rounded-2xl border bg-card p-6 shadow-soft-sm space-y-4" variants={fadeUp} initial="hidden" animate="visible" custom={1}>
            <h2 className="font-semibold">Configure Your Interview</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Job Title *</label>
                <Input placeholder="e.g. Senior Software Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} className="rounded-xl" />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium">Interview Type</label>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 sm:gap-1">
                  {INTERVIEW_TYPES.map((t) => (
                    <button key={t.value} onClick={() => setInterviewType(t.value)}
                      className={cn("rounded-lg border p-2 text-center text-2xs transition-all",
                        interviewType === t.value ? "border-primary bg-primary/5 font-medium" : "border-border hover:border-primary/30"
                      )}>
                      <t.icon className="h-3.5 w-3.5 mx-auto mb-0.5" />
                      <span className="block leading-tight">{t.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium">Difficulty</label>
                <Select value={difficulty} onValueChange={setDifficulty}>
                  <SelectTrigger className="rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["junior", "intermediate", "senior", "executive"].map((d) => (
                      <SelectItem key={d} value={d} className="capitalize">{d}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium">Questions</label>
                <Select value={String(questionCount)} onValueChange={(v) => setQuestionCount(Number(v))}>
                  <SelectTrigger className="rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[3, 5, 7, 10].map((n) => <SelectItem key={n} value={String(n)}>{n} questions</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button onClick={startSession} disabled={loading || !jobTitle.trim()} size="lg" className="w-full rounded-xl gap-2">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {loading ? "Generating Questions..." : `Start ${mode === "timed" ? "Timed " : mode === "mock" ? "Mock " : ""}Interview`}
            </Button>
          </motion.div>
        </motion.div>
      )}

      {/* ── Active Phase ────────────────────────────────────── */}
      {phase === "active" && questions.length > 0 && (
        <motion.div key="active" className="grid gap-6 lg:grid-cols-[1fr_300px]" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} transition={{ duration: 0.4 }}>
          {/* Main question area */}
          <div className="space-y-4">
            {/* Progress bar */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-primary to-violet-500"
                  animate={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
                {mode === "timed" && <TimerRing timeLeft={timeLeft} />}
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
                <span>{currentIdx + 1}/{questions.length}</span>
              </div>
            </div>

            {/* Question card */}
            <motion.div
              key={currentIdx}
              className="rounded-2xl border bg-card p-6 shadow-soft-sm space-y-4"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            >
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground text-sm font-bold">
                  Q{currentIdx + 1}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="secondary" className="text-[10px] uppercase">{questions[currentIdx].type || interviewType}</Badge>
                    {mode === "timed" && timeLeft <= 15 && <Badge variant="destructive" className="text-[10px] animate-pulse">Time running out!</Badge>}
                  </div>
                  <p className="text-base font-medium leading-relaxed">{questions[currentIdx].text}</p>
                  {questions[currentIdx].tips && (
                    <p className="text-xs text-muted-foreground mt-2 bg-muted/30 p-2 rounded-lg">
                      <Brain className="h-3 w-3 inline mr-1" /> {questions[currentIdx].tips}
                    </p>
                  )}
                </div>
              </div>

              <Textarea className="h-36 resize-none rounded-xl text-sm" placeholder="Type your answer... Use the STAR method: Situation → Task → Action → Result" value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={5000} />

              <div className="flex items-center justify-between">
                <span className="text-2xs text-muted-foreground">{answer.length}/5,000</span>
                <Button onClick={submitAnswer} disabled={submitting || (!answer.trim() && mode !== "timed")} className="rounded-xl gap-2">
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  {currentIdx < questions.length - 1 ? "Submit & Next" : "Submit & Finish"}
                </Button>
              </div>
            </motion.div>
          </div>

          {/* Side panel — Last answer feedback */}
          <div className="space-y-3">
            <AnimatePresence mode="wait">
            {lastAnswer ? (
              <motion.div key={answers.length} className="rounded-2xl border bg-card p-4 shadow-soft-sm space-y-3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4 }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Previous Answer</h3>
                  <ScoreRing value={lastAnswer.score} size={48} />
                </div>
                {lastAnswer.feedback && <p className="text-xs text-muted-foreground leading-relaxed">{lastAnswer.feedback}</p>}
                {lastAnswer.star_scores && (
                  <div className="space-y-1.5">
                    <p className="text-2xs font-medium text-muted-foreground uppercase tracking-wider">STAR Breakdown</p>
                    {Object.entries(lastAnswer.star_scores).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className="text-2xs text-muted-foreground w-16 capitalize">{key}</span>
                        <div className="flex-1 h-1.5 bg-muted/20 rounded-full overflow-hidden">
                          <motion.div
                            className={cn("h-full rounded-full", (val as number) >= 20 ? "bg-emerald-500" : (val as number) >= 15 ? "bg-amber-500" : "bg-rose-500")}
                            initial={{ width: 0 }}
                            animate={{ width: `${((val as number) / 25) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
                          />
                        </div>
                        <span className="text-2xs font-mono tabular-nums w-8 text-right">{val as number}/25</span>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-2xl border border-dashed bg-card/50 p-4 text-center">
                <Brain className="h-8 w-8 text-muted-foreground/20 mx-auto mb-2" />
                <p className="text-xs text-muted-foreground">AI feedback will appear here after your first answer</p>
              </motion.div>
            )}
            </AnimatePresence>

            {/* Quick tips */}
            <motion.div className="rounded-xl border bg-muted/30 p-3 space-y-1.5" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
              <p className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider">STAR Tips</p>
              <div className="space-y-1 text-2xs text-muted-foreground">
                <p><strong className="text-foreground">S</strong>ituation — Set the scene</p>
                <p><strong className="text-foreground">T</strong>ask — Your responsibility</p>
                <p><strong className="text-foreground">A</strong>ction — What YOU did</p>
                <p><strong className="text-foreground">R</strong>esult — Quantified outcome</p>
              </div>
            </motion.div>
          </div>
        </motion.div>
      )}

      {/* ── Review Phase ────────────────────────────────────── */}
      {phase === "review" && session && (
        <motion.div key="review" className="space-y-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} transition={{ duration: 0.4 }}>
          {/* AI Trace */}
          <AITrace
            variant="banner"
            items={[
              { label: `${questions.length} questions generated`, done: true },
              { label: `${answers.length} answers evaluated`, done: true },
              { label: `${interviewType} · ${difficulty} level`, done: true },
              { label: `${mode} mode`, done: true },
            ]}
          />
          {/* Score summary */}
          <motion.div className="rounded-2xl border bg-gradient-to-br from-primary/5 via-violet-500/5 to-transparent p-6 sm:p-8 shadow-soft-sm" initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.5 }}>
            <div className="flex flex-col md:flex-row items-center gap-8">
              <ScoreRing value={session.overall_score ?? 0} size={130} label="Overall Score" />
              <div className="flex-1 text-center md:text-left">
                <h2 className="text-2xl font-bold">Interview Complete!</h2>
                <p className="text-sm text-muted-foreground mt-1 max-w-md">
                  {(session.overall_score ?? 0) >= 80 ? "Excellent performance! You're well-prepared for this role." :
                   (session.overall_score ?? 0) >= 60 ? "Good effort! Focus on the areas below to improve." :
                   "Keep practicing — review the feedback below and try again."}
                </p>
                <div className="flex items-center gap-3 mt-3 justify-center md:justify-start">
                  <Badge variant="outline" className="text-xs">{interviewType}</Badge>
                  <Badge variant="outline" className="text-xs">{difficulty}</Badge>
                  <Badge variant="outline" className="text-xs">{questions.length} questions</Badge>
                  <Badge variant="outline" className="text-xs">{mode} mode</Badge>
                </div>
              </div>
              <Button onClick={restart} variant="outline" className="rounded-xl gap-2 shrink-0">
                <RotateCcw className="h-4 w-4" /> New Interview
              </Button>
            </div>
          </motion.div>

          {/* Answer reviews */}
          <motion.div className="space-y-3" variants={staggerContainer} initial="hidden" animate="visible">
            {answers.map((a, i) => (
              <motion.details key={i} variants={staggerItem} className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden group">
                <summary className="flex items-center gap-3 p-4 cursor-pointer list-none select-none hover:bg-muted/30 transition-colors">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-xs font-bold">Q{i + 1}</span>
                  <span className="flex-1 text-sm font-medium truncate">{questions[i]?.text?.slice(0, 80)}...</span>
                  <ScoreRing value={a.score} size={40} />
                  <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
                </summary>
                <div className="px-4 pb-4 pt-0 border-t space-y-3">
                  <div className="rounded-lg bg-muted/30 p-3"><p className="text-xs text-muted-foreground">{a.answer_text}</p></div>
                  {a.feedback && <p className="text-sm">{a.feedback}</p>}
                  {a.star_scores && (
                    <div className="grid grid-cols-4 gap-2">
                      {Object.entries(a.star_scores).map(([key, val]) => (
                        <div key={key} className="text-center rounded-lg border p-2">
                          <div className="text-2xs uppercase text-muted-foreground">{key}</div>
                          <div className={cn("text-sm font-bold", (val as number) >= 20 ? "text-emerald-500" : (val as number) >= 15 ? "text-amber-500" : "text-rose-500")}>{val as number}/25</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {a.model_answer && (
                    <details className="rounded-lg border bg-emerald-500/5 border-emerald-500/20 overflow-hidden">
                      <summary className="px-3 py-2 text-xs font-medium text-emerald-600 dark:text-emerald-400 cursor-pointer list-none select-none flex items-center gap-1">
                        <Trophy className="h-3 w-3" /> View Model Answer
                      </summary>
                      <div className="px-3 pb-3 text-xs text-muted-foreground">{a.model_answer}</div>
                    </details>
                  )}
                </div>
              </motion.details>
            ))}
          </motion.div>

          {/* Cross-link: Build a full application */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
            className="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/[0.04] to-transparent p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                  <Zap className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Ready to apply?</p>
                  <p className="text-xs text-muted-foreground">Create a full application workspace with tailored documents and gap analysis.</p>
                </div>
              </div>
              <Link href="/new">
                <Button size="sm" className="gap-2 rounded-xl shrink-0 whitespace-nowrap">
                  New Application
                </Button>
              </Link>
            </div>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>
    </div>
  );
}
