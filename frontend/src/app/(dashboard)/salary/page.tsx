"use client";

import React, { useState } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { SalaryAnalysis } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DollarSign, Loader2, TrendingUp, MessageSquare, ArrowUp, Target } from "lucide-react";

export default function SalaryCoachPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [yoe, setYoe] = useState("");
  const [currentSalary, setCurrentSalary] = useState("");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<SalaryAnalysis | null>(null);
  const [error, setError] = useState("");

  const analyze = async () => {
    if (!jobTitle.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.salary.analyze({
        job_title: jobTitle,
        company: company || undefined,
        location: location || undefined,
        experience_years: yoe ? parseInt(yoe) : undefined,
        current_salary: currentSalary ? parseInt(currentSalary) : undefined,
      });
      setAnalysis(result);
    } catch (e: any) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const fmt = (n: number) => "$" + n.toLocaleString();

  return (
    <div className="space-y-8 p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/10">
          <DollarSign className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Salary Coach</h1>
          <p className="text-xs text-muted-foreground">Market data, negotiation scripts, and counter-offer guidance</p>
        </div>
      </div>

      {/* Input Form */}
      <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="space-y-2">
            <label htmlFor="salary-job-title" className="text-sm font-medium">Job Title *</label>
            <Input id="salary-job-title" placeholder="e.g. Senior Software Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
          </div>
          <div className="space-y-2">
            <label htmlFor="salary-company" className="text-sm font-medium">Company</label>
            <Input id="salary-company" placeholder="e.g. Google" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="space-y-2">
            <label htmlFor="salary-location" className="text-sm font-medium">Location</label>
            <Input id="salary-location" placeholder="e.g. San Francisco, CA" value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
          <div className="space-y-2">
            <label htmlFor="salary-yoe" className="text-sm font-medium">Years of Experience</label>
            <Input id="salary-yoe" type="number" placeholder="e.g. 5" value={yoe} onChange={(e) => setYoe(e.target.value)} />
          </div>
          <div className="space-y-2">
            <label htmlFor="salary-current" className="text-sm font-medium">Current Salary ($)</label>
            <Input id="salary-current" type="number" placeholder="e.g. 120000" value={currentSalary} onChange={(e) => setCurrentSalary(e.target.value)} />
          </div>
        </div>
        <Button onClick={analyze} disabled={loading || !jobTitle.trim()} size="lg" className="w-full">
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <TrendingUp className="h-4 w-4 mr-2" />}
          {loading ? "Analyzing Market Data..." : "Analyze Salary"}
        </Button>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {analysis && (
        <div className="space-y-6">
          {/* Salary Range Visualization */}
          <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Target className="h-5 w-5" /> Market Salary Range
            </h2>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="rounded-lg bg-red-50 dark:bg-red-900/20 p-4">
                <div className="text-xs text-muted-foreground uppercase">Low (P25)</div>
                <div className="text-2xl font-bold text-red-600 dark:text-red-400">{fmt(analysis.market_data?.percentile_25 || 0)}</div>
              </div>
              <div className="rounded-lg bg-green-50 dark:bg-green-900/20 p-4 ring-2 ring-green-500">
                <div className="text-xs text-muted-foreground uppercase">Median (P50)</div>
                <div className="text-2xl font-bold text-green-600 dark:text-green-400">{fmt(analysis.market_data?.median || 0)}</div>
              </div>
              <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 p-4">
                <div className="text-xs text-muted-foreground uppercase">High (P75)</div>
                <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{fmt(analysis.market_data?.percentile_75 || 0)}</div>
              </div>
            </div>

            {/* Range Bar */}
            <div className="relative h-8 bg-gradient-to-r from-red-200 via-green-200 to-blue-200 dark:from-red-900/40 dark:via-green-900/40 dark:to-blue-900/40 rounded-full">
              {currentSalary && analysis.market_data?.percentile_25 && analysis.market_data?.percentile_75 && (
                <div
                  className="absolute top-0 h-8 w-1 bg-black dark:bg-white rounded"
                  style={{
                    left: `${Math.min(100, Math.max(0,
                      ((parseInt(currentSalary) - analysis.market_data.percentile_25) /
                        (analysis.market_data.percentile_75 - analysis.market_data.percentile_25)) * 100
                    ))}%`,
                  }}
                  title={`Your salary: ${fmt(parseInt(currentSalary))}`}
                />
              )}
            </div>
            {currentSalary && <p className="text-xs text-muted-foreground text-center">Your current salary: {fmt(parseInt(currentSalary))}</p>}
          </div>

          {/* Recommended Target */}
          {analysis.salary_range?.target && (
            <div className="rounded-2xl border-2 border-primary p-6 text-center space-y-2 shadow-soft-sm">
              <ArrowUp className="h-8 w-8 text-primary mx-auto" />
              <div className="text-sm text-muted-foreground">Your Recommended Target</div>
              <div className="text-4xl font-bold text-primary">{fmt(analysis.salary_range.target)}</div>
              <div className="text-sm text-muted-foreground">
                Range: {fmt(analysis.salary_range.recommended_min)} — {fmt(analysis.salary_range.recommended_max)}
              </div>
              {analysis.salary_range.reasoning && (
                <p className="text-xs text-muted-foreground mt-1">{analysis.salary_range.reasoning}</p>
              )}
            </div>
          )}

          {/* Negotiation Scripts */}
          {analysis.negotiation_scripts && analysis.negotiation_scripts.length > 0 && (
            <div className="rounded-2xl border p-6 space-y-4 shadow-soft-sm">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <MessageSquare className="h-5 w-5" /> Negotiation Scripts
              </h2>
              <div className="space-y-4">
                {analysis.negotiation_scripts.map((script, i) => (
                  <div key={i} className="rounded-lg bg-muted/30 p-4 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] px-2 py-0.5 rounded-lg bg-primary/10 text-primary font-medium">{script.scenario}</span>
                    </div>
                    <p className="text-sm italic leading-relaxed">&ldquo;{script.opening_line}&rdquo;</p>
                    {script.key_points && script.key_points.length > 0 && (
                      <ul className="text-sm text-muted-foreground list-disc list-inside space-y-1">
                        {script.key_points.map((pt, j) => <li key={j}>{pt}</li>)}
                      </ul>
                    )}
                    <p className="text-sm italic text-muted-foreground">&ldquo;{script.closing_line}&rdquo;</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Counter Offer Guidance */}
          {analysis.counter_offers && analysis.counter_offers.length > 0 && (
            <div className="rounded-2xl border p-6 space-y-3 shadow-soft-sm">
              <h2 className="text-xl font-semibold">Counter-Offer Strategy</h2>
              <div className="space-y-3">
                {analysis.counter_offers.map((co, i) => (
                  <div key={i} className="rounded-lg bg-muted/30 p-4 space-y-2">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div><span className="text-muted-foreground">If offered:</span> <span className="font-medium">{fmt(co.if_offered)}</span></div>
                      <div><span className="text-muted-foreground">Counter with:</span> <span className="font-bold text-primary">{fmt(co.counter_with)}</span></div>
                    </div>
                    <p className="text-sm text-muted-foreground">{co.justification}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
