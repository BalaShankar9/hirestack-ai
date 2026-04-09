"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { SalaryAnalysis } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  DollarSign, Loader2, TrendingUp, MessageSquare, ArrowUp,
  Target, Copy, Zap, Shield, BarChart3, ChevronDown,
  Briefcase, Send, Bot, CheckCircle, AlertTriangle, Info,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { AITrace } from "@/components/ui/ai-trace";

function fmt(n: number, currency = "$") {
  return `${currency}${n.toLocaleString()}`;
}

export default function SalaryCoachPage() {
  const { user, session: authSession } = useAuth();
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [yoe, setYoe] = useState("");
  const [currentSalary, setCurrentSalary] = useState("");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<any>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [profileSkills, setProfileSkills] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Auto-fill from saved profile
  useEffect(() => {
    const token = authSession?.access_token;
    if (!token) return;
    api.setToken(token);
    api.profile.get().then((p: any) => {
      if (!p) return;
      setJobTitle(prev => p.title && !prev ? p.title : prev);
      const contact = p.contact_info || {};
      setLocation(prev => contact.location && !prev ? contact.location : prev);
      const skills = (p.skills || []).map((s: any) => typeof s === "string" ? s : s.name).join(", ");
      setProfileSkills(skills);
      // Estimate YoE from experience
      setYoe(prev => {
        if (!prev && p.experience?.length) {
          let years = 0;
          for (const e of p.experience) {
            if (e?.start_date) {
              try { years += Math.max(0, (parseInt(String(e.end_date || "2026").slice(0, 4)) - parseInt(String(e.start_date).slice(0, 4)))); } catch {}
            }
          }
          if (years > 0) return String(years);
        }
        return prev;
      });
    }).catch(() => {});
  }, [authSession?.access_token]);

  const analyze = async () => {
    if (!jobTitle.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.salary.analyze({
        job_title: jobTitle,
        company: company || undefined,
        location: location || undefined,
        years_experience: yoe ? parseInt(yoe) : undefined,
        current_salary: currentSalary ? parseInt(currentSalary) : undefined,
        skills_summary: profileSkills || undefined,
      });
      setAnalysis(result);
      setActiveTab("overview");
    } catch (e: any) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const copyText = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied!" });
  };

  const market = analysis?.market_data || analysis?.market_analysis || {};
  const salaryRange = analysis?.salary_range || analysis?.candidate_value_assessment || {};
  const scripts = analysis?.negotiation_scripts || [];
  const counters = analysis?.counter_offers || [];
  const talkingPoints = analysis?.talking_points || [];
  const strategy = analysis?.negotiation_strategy || {};
  const overall = analysis?.overall_assessment || "";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 shadow-glow-sm">
          <DollarSign className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Salary Negotiation Coach</h1>
          <p className="text-sm text-muted-foreground">Market intelligence, negotiation scripts, and counter-offer strategy</p>
        </div>
      </div>

      {/* Input — Progressive disclosure: essential first, optional behind toggle */}
      <div className="rounded-2xl border bg-card p-6 shadow-soft-sm space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="space-y-1"><label className="text-2xs font-medium">Job Title *</label><Input placeholder="Senior Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
          <div className="space-y-1"><label className="text-2xs font-medium">Company</label><Input placeholder="Google" value={company} onChange={(e) => setCompany(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
          <div className="space-y-1"><label className="text-2xs font-medium">Location</label><Input placeholder="London, UK" value={location} onChange={(e) => setLocation(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
        </div>
        {/* Advanced fields — hidden until requested */}
        {showAdvanced ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border-t pt-3">
            <div className="space-y-1"><label className="text-2xs font-medium">Years of Experience</label><Input type="number" placeholder="5" value={yoe} onChange={(e) => setYoe(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
            <div className="space-y-1"><label className="text-2xs font-medium">Current Salary <span className="text-muted-foreground">(optional — improves targeting)</span></label><Input type="number" placeholder="80000" value={currentSalary} onChange={(e) => setCurrentSalary(e.target.value)} className="rounded-xl h-9 text-sm" /></div>
          </div>
        ) : (
          <button onClick={() => setShowAdvanced(true)} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
            <Info className="h-3 w-3" /> Add experience &amp; current salary for more accurate results
          </button>
        )}
        <Button onClick={analyze} disabled={loading || !jobTitle.trim()} className="w-full rounded-xl gap-2">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingUp className="h-4 w-4" />}
          {loading ? "Analyzing market data..." : "Analyze Salary & Generate Scripts"}
        </Button>
      </div>

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}

      {/* Results */}
      {analysis && (
        <div className="space-y-4 animate-fade-in">
          {/* AI Trace */}
          <AITrace
            variant="banner"
            items={[
              `Analyzed ${jobTitle}${company ? ` at ${company}` : ""}${location ? ` in ${location}` : ""}`,
              `${scripts.length} negotiation scripts`,
              `${counters.length} counter-offer scenarios`,
              `${talkingPoints.length} talking points`,
            ]}
          />
          {/* Tab navigation */}
          <div className="flex gap-1 rounded-xl bg-muted/50 p-1 overflow-x-auto">
            {[
              { key: "overview", label: "Market Overview", icon: BarChart3 },
              { key: "scripts", label: "Negotiation Scripts", icon: MessageSquare },
              { key: "counter", label: "Counter Strategy", icon: Shield },
              { key: "talking", label: "Talking Points", icon: Zap },
            ].map((tab) => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                className={cn("flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all whitespace-nowrap",
                  activeTab === tab.key ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}>
                <tab.icon className="h-3.5 w-3.5" /> {tab.label}
              </button>
            ))}
          </div>

          {/* Overview Tab */}
          {activeTab === "overview" && (
            <div className="space-y-4">
              {/* Salary Range Cards */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-2xl border bg-rose-500/5 border-rose-500/20 p-5 text-center">
                  <p className="text-2xs text-muted-foreground uppercase tracking-wider">Low (P25)</p>
                  <p className="text-2xl font-bold text-rose-500 tabular-nums mt-1">{fmt(market.low || market.percentile_25 || 0)}</p>
                </div>
                <div className="rounded-2xl border-2 border-emerald-500 bg-emerald-500/5 p-5 text-center shadow-glow-sm">
                  <p className="text-2xs text-muted-foreground uppercase tracking-wider">Median</p>
                  <p className="text-3xl font-bold text-emerald-500 tabular-nums mt-1">{fmt(market.median || 0)}</p>
                </div>
                <div className="rounded-2xl border bg-blue-500/5 border-blue-500/20 p-5 text-center">
                  <p className="text-2xs text-muted-foreground uppercase tracking-wider">High (P75)</p>
                  <p className="text-2xl font-bold text-blue-500 tabular-nums mt-1">{fmt(market.high || market.percentile_75 || 0)}</p>
                </div>
              </div>

              {/* Range bar */}
              <div className="rounded-2xl border bg-card p-5 space-y-3">
                <div className="relative h-4 rounded-full bg-gradient-to-r from-rose-500/30 via-emerald-500/30 to-blue-500/30 overflow-hidden">
                  <div className="absolute inset-y-0 left-1/2 w-0.5 bg-emerald-500" />
                  {currentSalary && market.low && market.high && (
                    <div className="absolute top-0 h-4 w-1.5 bg-foreground rounded-full" style={{
                      left: `${Math.min(95, Math.max(5, ((parseInt(currentSalary) - (market.low || 0)) / ((market.high || 1) - (market.low || 0))) * 100))}%`,
                    }} title={`Your salary: ${fmt(parseInt(currentSalary))}`} />
                  )}
                </div>
                <div className="flex justify-between text-2xs text-muted-foreground font-mono">
                  <span>{fmt(market.low || market.percentile_25 || 0)}</span>
                  <span className="font-bold text-foreground">{fmt(market.median || 0)}</span>
                  <span>{fmt(market.high || market.percentile_75 || 0)}</span>
                </div>
              </div>

              {/* Recommended target */}
              {(salaryRange.target || salaryRange.recommended_ask || salaryRange.estimated_range_high) && (
                <div className="rounded-2xl border-2 border-primary bg-primary/5 p-6 text-center">
                  <ArrowUp className="h-6 w-6 text-primary mx-auto mb-2" />
                  <p className="text-xs text-muted-foreground uppercase">Your Target</p>
                  <p className="text-4xl font-bold text-primary tabular-nums mt-1">
                    {fmt(salaryRange.target || salaryRange.recommended_ask || salaryRange.estimated_range_high || 0)}
                  </p>
                  {salaryRange.recommended_min && salaryRange.recommended_max && (
                    <p className="text-sm text-muted-foreground mt-1">Range: {fmt(salaryRange.recommended_min)} — {fmt(salaryRange.recommended_max)}</p>
                  )}
                </div>
              )}

              {overall && (
                <div className="rounded-xl border bg-muted/30 p-4">
                  <p className="text-sm leading-relaxed">{overall}</p>
                </div>
              )}
            </div>
          )}

          {/* Scripts Tab */}
          {activeTab === "scripts" && (
            <div className="space-y-3">
              {scripts.length > 0 ? scripts.map((s: any, i: number) => (
                <div key={i} className="rounded-2xl border bg-card p-5 shadow-soft-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary" className="text-xs">{s.scenario || `Script ${i + 1}`}</Badge>
                    <button onClick={() => copyText(`${s.opening_line || ""}\n${(s.key_points || []).join("\n")}\n${s.closing_line || ""}`)} className="text-muted-foreground hover:text-foreground">
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  {s.opening_line && <p className="text-sm italic border-l-2 border-primary pl-3">&ldquo;{s.opening_line}&rdquo;</p>}
                  {s.key_points?.length > 0 && (
                    <ul className="space-y-1">
                      {s.key_points.map((pt: string, j: number) => (
                        <li key={j} className="text-xs flex items-start gap-2"><CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /> {pt}</li>
                      ))}
                    </ul>
                  )}
                  {s.closing_line && <p className="text-sm italic text-muted-foreground border-l-2 border-muted pl-3">&ldquo;{s.closing_line}&rdquo;</p>}
                </div>
              )) : <p className="text-sm text-muted-foreground text-center py-8">No scripts generated. Try the analysis again.</p>}
            </div>
          )}

          {/* Counter Tab */}
          {activeTab === "counter" && (
            <div className="space-y-3">
              {counters.length > 0 ? counters.map((co: any, i: number) => (
                <div key={i} className="rounded-2xl border bg-card p-4 shadow-soft-sm">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="rounded-xl bg-muted/30 p-3 text-center">
                      <p className="text-2xs text-muted-foreground">If offered</p>
                      <p className="text-lg font-bold tabular-nums">{fmt(co.if_offered || 0)}</p>
                    </div>
                    <div className="rounded-xl bg-emerald-500/10 p-3 text-center">
                      <p className="text-2xs text-emerald-500">Counter with</p>
                      <p className="text-lg font-bold text-emerald-500 tabular-nums">{fmt(co.counter_with || 0)}</p>
                    </div>
                  </div>
                  {co.justification && <p className="text-xs text-muted-foreground mt-3">{co.justification}</p>}
                </div>
              )) : (
                <div className="rounded-2xl border border-dashed p-8 text-center">
                  <Shield className="h-8 w-8 text-muted-foreground/20 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">Counter-offer strategies will appear here</p>
                </div>
              )}

              {/* Strategy summary */}
              {strategy.approach && (
                <div className="rounded-xl border bg-primary/5 border-primary/20 p-4">
                  <p className="text-xs font-semibold text-primary mb-1">Negotiation Strategy</p>
                  <p className="text-xs text-muted-foreground">{strategy.approach}</p>
                  {strategy.timing && <p className="text-xs text-muted-foreground mt-1"><strong>Timing:</strong> {strategy.timing}</p>}
                </div>
              )}
            </div>
          )}

          {/* Talking Points Tab */}
          {activeTab === "talking" && (
            <div className="space-y-2">
              {talkingPoints.length > 0 ? talkingPoints.map((tp: any, i: number) => {
                const text = typeof tp === "string" ? tp : tp.point || tp.description || JSON.stringify(tp);
                return (
                  <div key={i} className="flex items-start gap-3 rounded-xl border bg-card p-3 hover:shadow-soft-sm transition-shadow group">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-2xs font-bold text-primary">{i + 1}</span>
                    <p className="text-sm flex-1">{text}</p>
                    <button onClick={() => copyText(text)} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground transition-opacity">
                      <Copy className="h-3 w-3" />
                    </button>
                  </div>
                );
              }) : (
                <div className="rounded-2xl border border-dashed p-8 text-center">
                  <Zap className="h-8 w-8 text-muted-foreground/20 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">Talking points will be generated with your analysis</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!analysis && !loading && (
        <div className="rounded-2xl border border-dashed bg-card/50 p-8">
          <div className="flex flex-col md:flex-row items-center gap-6 text-center md:text-left">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 shrink-0">
              <DollarSign className="h-7 w-7 text-emerald-500" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">Know Your Worth</h3>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-lg">
                Enter a job title and location to get AI-powered salary analysis: market ranges, negotiation scripts,
                counter-offer strategies, and talking points — all tailored to your experience level.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
