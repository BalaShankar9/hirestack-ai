"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import { toast } from "@/hooks/use-toast";
import api from "@/lib/api";
import type { InterviewSession, InterviewQuestion, InterviewAnswer } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Mic, Play, Send, CheckCircle, Clock, Loader2, RotateCcw, ChevronRight } from "lucide-react";

type Phase = "setup" | "active" | "review";

export default function InterviewSimulatorPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;
  const [phase, setPhase] = useState<Phase>("setup");

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
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);

  // P1-9: Elapsed timer
  useEffect(() => {
    if (phase !== "active") return;
    setElapsed(0);
    const interval = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(interval);
  }, [phase, currentIdx]);

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
      });
      setSession(result.session);
      setQuestions(result.questions);
      setCurrentIdx(0);
      setAnswers([]);
      setPhase("active");
      toast({ title: "Interview started", description: `${result.questions.length} questions ready. Good luck!`, variant: "success" });
    } catch (e: any) {
      setError(e.message || "Failed to start");
    } finally {
      setLoading(false);
    }
  };

  const submitAnswer = async () => {
    if (!session || !answer.trim()) return;
    setSubmitting(true);
    try {
      const result = await api.interview.submitAnswer(session.id, {
        question_index: currentIdx,
        answer_text: answer,
      });
      setAnswers((prev) => [...prev, result]);
      setAnswer("");
      if (currentIdx < questions.length - 1) {
        setCurrentIdx((prev) => prev + 1);
      } else {
        // Complete session
        const completed = await api.interview.complete(session.id);
        setSession(completed);
        setPhase("review");
      }
    } catch (e: any) {
      setError(e.message || "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  const restart = () => {
    setPhase("setup");
    setSession(null);
    setQuestions([]);
    setAnswers([]);
    setCurrentIdx(0);
    setAnswer("");
  };

  return (
    <div className="space-y-8 p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-rose-500/10">
          <Mic className="h-5 w-5 text-rose-600 dark:text-rose-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Interview Simulator</h1>
          <p className="text-xs text-muted-foreground">Practice with AI-generated questions and get STAR-method feedback</p>
        </div>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {/* Setup Phase */}
      {phase === "setup" && (
        <div className="space-y-6 rounded-2xl border p-6 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
          <h2 className="text-xl font-semibold">Configure Your Interview</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label htmlFor="interview-job-title" className="text-sm font-medium">Job Title *</label>
              <Input
                id="interview-job-title"
                placeholder="e.g. Senior Software Engineer"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="interview-type" className="text-sm font-medium">Interview Type</label>
              <Select value={interviewType} onValueChange={setInterviewType}>
                <SelectTrigger id="interview-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="behavioral">Behavioral</SelectItem>
                  <SelectItem value="technical">Technical</SelectItem>
                  <SelectItem value="situational">Situational</SelectItem>
                  <SelectItem value="mixed">Mixed</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label htmlFor="interview-difficulty" className="text-sm font-medium">Difficulty</label>
              <Select value={difficulty} onValueChange={setDifficulty}>
                <SelectTrigger id="interview-difficulty" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="junior">Junior</SelectItem>
                  <SelectItem value="intermediate">Intermediate</SelectItem>
                  <SelectItem value="senior">Senior</SelectItem>
                  <SelectItem value="executive">Executive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label htmlFor="interview-questions" className="text-sm font-medium">Questions</label>
              <Select value={String(questionCount)} onValueChange={(v) => setQuestionCount(Number(v))}>
                <SelectTrigger id="interview-questions" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[3, 5, 7, 10].map((n) => (
                    <SelectItem key={n} value={String(n)}>{n} questions</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button onClick={startSession} disabled={loading || !jobTitle.trim()} size="lg" className="w-full">
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Play className="h-4 w-4 mr-2" />}
            {loading ? "Generating Questions..." : "Start Interview"}
          </Button>
        </div>
      )}

      {/* Active Phase */}
      {phase === "active" && questions.length > 0 && (
        <div className="space-y-6">
          {/* Progress */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-muted">
              <div
                className="h-2 rounded-full bg-primary transition-all"
                style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
              />
            </div>
            <span className="text-sm text-muted-foreground font-medium flex items-center gap-2">
              <Clock className="h-4 w-4" />
              {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
              <span className="mx-1">•</span>
              {currentIdx + 1} / {questions.length}
            </span>
          </div>

          {/* Question Card */}
          <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
            <div className="flex items-start gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
                Q{currentIdx + 1}
              </span>
              <div>
                <span className="text-[11px] px-2 py-0.5 rounded-lg bg-muted font-medium uppercase">
                  {questions[currentIdx].type || interviewType}
                </span>
                <p className="text-lg font-medium mt-2">{questions[currentIdx].text}</p>
                {questions[currentIdx].tips && (
                  <p className="text-sm text-muted-foreground mt-1">{questions[currentIdx].tips}</p>
                )}
              </div>
            </div>

            <Textarea
              className="h-40 resize-none"
              placeholder="Type your answer... Use the STAR method: Situation, Task, Action, Result"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              maxLength={5000}
            />

            <Button onClick={submitAnswer} disabled={submitting || !answer.trim()} className="w-full">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              {currentIdx < questions.length - 1 ? "Submit & Next" : "Submit & Finish"}
            </Button>
          </div>
        </div>
      )}

      {/* Review Phase */}
      {phase === "review" && session && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="rounded-2xl border p-6 text-center space-y-3 shadow-soft-sm">
            <CheckCircle className="h-12 w-12 text-green-500 dark:text-green-400 mx-auto" />
            <h2 className="text-2xl font-bold">Interview Complete!</h2>
            {session.overall_score !== undefined && (
              <div className="text-4xl font-bold text-primary">{session.overall_score}/100</div>
            )}
            {session.overall_feedback && <p className="text-muted-foreground max-w-lg mx-auto">{session.overall_feedback}</p>}
          </div>

          {/* Answer Reviews */}
          <div className="space-y-4">
            {answers.map((a, i) => (
              <div key={i} className="rounded-2xl border p-5 space-y-3 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Q{i + 1}: {questions[i]?.text?.slice(0, 80)}...</h3>
                  <span className={`text-lg font-bold ${
                    a.score >= 80 ? "text-green-600 dark:text-green-400" : a.score >= 60 ? "text-yellow-600 dark:text-yellow-400" : "text-red-600 dark:text-red-400"
                  }`}>
                    {a.score}/100
                  </span>
                </div>
                <p className="text-sm bg-muted/50 p-3 rounded-lg">{a.answer_text}</p>
                {a.feedback && <p className="text-sm text-muted-foreground">{a.feedback}</p>}
                {a.star_scores && (
                  <div className="grid grid-cols-4 gap-2">
                    {Object.entries(a.star_scores).map(([key, val]) => (
                      <div key={key} className="text-center p-2 rounded-lg bg-muted/30">
                        <div className="text-[11px] uppercase text-muted-foreground">{key}</div>
                        <div className="font-bold">{val as number}/25</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <Button onClick={restart} variant="outline" size="lg" className="w-full">
            <RotateCcw className="h-4 w-4 mr-2" /> Start New Interview
          </Button>
        </div>
      )}
    </div>
  );
}
