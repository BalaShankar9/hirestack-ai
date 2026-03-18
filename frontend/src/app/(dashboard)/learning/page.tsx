"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { LearningChallenge, LearningStreak } from "@/types";
import { Button } from "@/components/ui/button";
import { Zap, Loader2, CheckCircle, XCircle, Flame, Trophy, Star, RefreshCw } from "lucide-react";

export default function LearningPage() {
  const { user } = useAuth();
  const [streak, setStreak] = useState<LearningStreak | null>(null);
  const [challenges, setChallenges] = useState<LearningChallenge[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [answerResult, setAnswerResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [streakRes, todayRes] = await Promise.all([
        api.learning.getStreak(),
        api.learning.getToday(),
      ]);
      setStreak(streakRes);
      setChallenges(todayRes || []);
      setCurrentIdx(0);
      setSelectedAnswer(null);
      setAnswerResult(null);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const generateChallenges = async () => {
    setGenerating(true);
    setError("");
    try {
      const result = await api.learning.generate();
      setChallenges(result || []);
      setCurrentIdx(0);
      setSelectedAnswer(null);
      setAnswerResult(null);
      // Refresh streak
      const s = await api.learning.getStreak();
      setStreak(s);
    } catch (e: any) {
      setError(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const submitAnswer = async (challengeId: string, answer: string) => {
    setSelectedAnswer(answer);
    try {
      const result = await api.learning.submitAnswer(challengeId, answer);
      setAnswerResult(result);
      // Refresh streak
      const s = await api.learning.getStreak();
      setStreak(s);
    } catch (e: any) {
      setError(e.message || "Submit failed");
    }
  };

  const nextChallenge = () => {
    setCurrentIdx((prev) => prev + 1);
    setSelectedAnswer(null);
    setAnswerResult(null);
  };

  const current = challenges[currentIdx];
  const allDone = currentIdx >= challenges.length && challenges.length > 0;

  return (
    <div className="space-y-8 p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <Zap className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Micro-Learning</h1>
          <p className="text-muted-foreground">Daily skill challenges with streak tracking</p>
        </div>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {/* Streak Banner */}
      {streak && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-xl border p-4 text-center bg-gradient-to-br from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20">
            <Flame className="h-8 w-8 text-orange-500 mx-auto mb-1" />
            <div className="text-3xl font-bold text-orange-600">{streak.current_streak || 0}</div>
            <div className="text-xs text-muted-foreground">Day Streak</div>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <Trophy className="h-8 w-8 text-yellow-500 mx-auto mb-1" />
            <div className="text-3xl font-bold">{streak.longest_streak || 0}</div>
            <div className="text-xs text-muted-foreground">Best Streak</div>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <Star className="h-8 w-8 text-primary mx-auto mb-1" />
            <div className="text-3xl font-bold">{streak.total_points || 0}</div>
            <div className="text-xs text-muted-foreground">Total Points</div>
          </div>
          <div className="rounded-xl border p-4 text-center">
            <div className="text-4xl mb-1">
              {(streak.level || 1) <= 3 ? "🌱" : (streak.level || 1) <= 7 ? "🌿" : (streak.level || 1) <= 15 ? "🌳" : "🏆"}
            </div>
            <div className="text-3xl font-bold">Lv.{streak.level || 1}</div>
            <div className="text-xs text-muted-foreground">Level</div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : challenges.length === 0 ? (
        <div className="text-center py-16 rounded-2xl border border-dashed bg-gradient-to-b from-muted/30 to-transparent">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 mb-4">
            <Zap className="h-7 w-7 text-primary" />
          </div>
          <h3 className="text-sm font-semibold">No challenges for today yet</h3>
          <p className="mt-1 text-xs text-muted-foreground max-w-xs mx-auto">
            Generate micro-learning challenges to sharpen your skills daily.
          </p>
          <Button onClick={generateChallenges} disabled={generating} size="lg" className="mt-5 gap-2 rounded-xl">
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Generate Today&apos;s Challenges
          </Button>
        </div>
      ) : allDone ? (
        <div className="text-center py-12 space-y-4 rounded-xl border bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20">
          <CheckCircle className="h-16 w-16 text-green-500 mx-auto" />
          <h2 className="text-2xl font-bold">All Done! 🎉</h2>
          <p className="text-muted-foreground">You completed all {challenges.length} challenges for today.</p>
          <Button onClick={generateChallenges} disabled={generating} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" /> Generate More
          </Button>
        </div>
      ) : current && (
        <div className="space-y-6">
          {/* Progress */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-muted">
              <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${((currentIdx + 1) / challenges.length) * 100}%` }} />
            </div>
            <span className="text-sm text-muted-foreground font-medium">{currentIdx + 1}/{challenges.length}</span>
          </div>

          {/* Challenge Card */}
          <div className="rounded-xl border p-6 space-y-5">
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                current.challenge_type === "quiz" ? "bg-blue-100 text-blue-700" :
                current.challenge_type === "scenario" ? "bg-purple-100 text-purple-700" :
                "bg-green-100 text-green-700"
              }`}>
                {current.challenge_type || "quiz"}
              </span>
              <span className="text-xs text-muted-foreground">{current.skill}</span>
              {current.points_earned > 0 && <span className="text-xs ml-auto font-medium">+{current.points_earned} pts</span>}
            </div>

            <p className="text-lg font-medium">{current.question}</p>

            {/* Options */}
            {current.options && current.options.length > 0 && (
              <div className="space-y-2">
                {current.options.map((opt: string, i: number) => {
                  const letter = String.fromCharCode(65 + i);
                  const isSelected = selectedAnswer === letter;
                  const isCorrect = answerResult?.correct_answer === letter;
                  const isWrong = isSelected && answerResult && !answerResult.is_correct;

                  return (
                    <button
                      key={i}
                      className={`w-full text-left p-4 rounded-lg border-2 transition-all flex items-center gap-3 ${
                        isCorrect && answerResult
                          ? "border-green-500 bg-green-50 dark:bg-green-900/20"
                          : isWrong
                          ? "border-red-500 bg-red-50 dark:bg-red-900/20"
                          : isSelected
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                      onClick={() => !answerResult && submitAnswer(current.id, letter)}
                      disabled={!!answerResult}
                    >
                      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                        isCorrect && answerResult
                          ? "bg-green-500 text-white"
                          : isWrong
                          ? "bg-red-500 text-white"
                          : "bg-muted"
                      }`}>
                        {isCorrect && answerResult ? <CheckCircle className="h-4 w-4" /> : isWrong ? <XCircle className="h-4 w-4" /> : letter}
                      </span>
                      <span className="text-sm">{opt}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Freeform input for scenario/flashcard */}
            {(!current.options || current.options.length === 0) && !answerResult && (
              <div className="space-y-3">
                <textarea
                  className="w-full h-32 rounded-lg border bg-background p-3 text-sm resize-none"
                  placeholder="Type your answer..."
                  value={selectedAnswer || ""}
                  onChange={(e) => setSelectedAnswer(e.target.value)}
                  maxLength={5000}
                />
                <Button onClick={() => selectedAnswer && submitAnswer(current.id, selectedAnswer)} disabled={!selectedAnswer?.trim()}>
                  Submit Answer
                </Button>
              </div>
            )}

            {/* Feedback */}
            {answerResult && (
              <div className={`rounded-lg p-4 ${answerResult.is_correct ? "bg-green-50 dark:bg-green-900/20" : "bg-red-50 dark:bg-red-900/20"}`}>
                <div className="flex items-center gap-2 mb-2">
                  {answerResult.is_correct ? (
                    <><CheckCircle className="h-5 w-5 text-green-600" /><span className="font-semibold text-green-600">Correct! +{answerResult.points_earned || 0} pts</span></>
                  ) : (
                    <><XCircle className="h-5 w-5 text-red-600" /><span className="font-semibold text-red-600">Incorrect</span></>
                  )}
                </div>
                {answerResult.explanation && <p className="text-sm text-muted-foreground">{answerResult.explanation}</p>}
              </div>
            )}

            {/* Next Button */}
            {answerResult && (
              <Button onClick={nextChallenge} className="w-full">
                {currentIdx < challenges.length - 1 ? "Next Challenge →" : "Finish 🎉"}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
