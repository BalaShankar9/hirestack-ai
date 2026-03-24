"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Fingerprint, Upload, FileText, Brain, ShieldCheck, Settings,
  Linkedin, Github, Globe, Mail, Phone, MapPin, Plus, Pencil, Trash2,
  Loader2, CheckCircle, AlertCircle, RefreshCw, Download, Eye,
  ChevronDown, ChevronUp, Award, Briefcase, GraduationCap, Code,
  BarChart3, TrendingUp, Target, Sparkles, X, ExternalLink,
  Link2, Zap, BookOpen, Twitter,
} from "lucide-react";
import { useAuth } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { sanitizeHtml } from "@/lib/sanitize";
import api from "@/lib/api";
import { exportToPdf } from "@/lib/export";
import type {
  Profile, ProfileCompleteness, ResumeWorthScore, AggregateGapAnalysis,
} from "@/types";

// ── Completion Ring SVG ──────────────────────────────────────────────

function CompletionRing({ score, size = 80 }: { score: number; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? "text-emerald-500" : score >= 50 ? "text-teal-500" : "text-amber-500";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={4} className="text-muted/20" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={4} strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className={cn("transition-all duration-700", color)} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-bold tabular-nums">{score}%</span>
      </div>
    </div>
  );
}

// ── Skill Level Dots ─────────────────────────────────────────────────

function SkillDots({ level }: { level?: string }) {
  const levels = ["beginner", "intermediate", "advanced", "expert"];
  const idx = levels.indexOf((level || "intermediate").toLowerCase());
  const filled = idx >= 0 ? idx + 1 : 2;
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className={cn("h-2 w-2 rounded-full", n <= filled ? "bg-teal-500" : "bg-muted/30")} />
      ))}
    </div>
  );
}

// ── Resume Worth Gauge ───────────────────────────────────────────────

function ResumeWorthGauge({ data }: { data: ResumeWorthScore | null }) {
  if (!data) return null;
  const { score, label, breakdown } = data;
  const color = score >= 85 ? "text-emerald-500" : score >= 65 ? "text-teal-500" : score >= 40 ? "text-amber-500" : "text-rose-500";
  const r = 56;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative" style={{ width: 128, height: 128 }}>
        <svg width={128} height={128} className="-rotate-90">
          <circle cx={64} cy={64} r={r} fill="none" stroke="currentColor" strokeWidth={6} className="text-muted/15" />
          <circle cx={64} cy={64} r={r} fill="none" stroke="currentColor" strokeWidth={6} strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className={cn("transition-all duration-1000", color)} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-3xl font-bold tabular-nums", color)}>{score}</span>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
        </div>
      </div>
      {breakdown && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          {Object.entries(breakdown).map(([key, val]) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground capitalize">{key.replace(/_/g, " ")}</span>
              <span className="font-medium tabular-nums">{val as number}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Paper Container ──────────────────────────────────────────────────

function PaperContainer({ html, title, documentType }: { html: string; title: string; documentType?: string }) {
  const cssType = documentType || "resume";
  const { getDocumentCSS } = require("@/lib/document-styles");
  const css = getDocumentCSS(cssType);

  return (
    <div className="mx-auto max-w-[860px]">
      {/* Branded accent bar */}
      <div className="h-1 bg-gradient-to-r from-indigo-600 via-violet-500 to-teal-500 rounded-t-lg" />
      <div
        className="bg-white text-black shadow-2xl rounded-b-lg overflow-y-auto relative"
        style={{ padding: "56px 52px", minHeight: 500 }}
      >
        <style dangerouslySetInnerHTML={{ __html: css }} />
        <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }} />
      </div>
    </div>
  );
}

// ── Accordion Section ────────────────────────────────────────────────

function AccordionSection({
  title, icon: Icon, count, children, defaultOpen = false, badge,
}: {
  title: string; icon: React.ElementType; count?: number; children: React.ReactNode; defaultOpen?: boolean; badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border bg-card shadow-soft-sm">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between p-4 text-left hover:bg-muted/30 rounded-2xl transition-colors">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10">
            <Icon className="h-4 w-4 text-teal-500" />
          </div>
          <span className="font-semibold">{title}</span>
          {count !== undefined && <Badge variant="secondary" className="text-xs">{count}</Badge>}
          {badge}
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && <div className="border-t px-4 pb-4 pt-3">{children}</div>}
    </div>
  );
}

// ── Social Connection Card ───────────────────────────────────────────

const SOCIAL_PLATFORMS = [
  {
    key: "linkedin" as const,
    label: "LinkedIn",
    icon: Linkedin,
    color: "bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-600/20",
    hoverColor: "hover:border-blue-500/40 hover:bg-blue-500/5",
    placeholder: "https://linkedin.com/in/yourname",
    benefit: "Work history, endorsements, certifications, recommendations",
  },
  {
    key: "github" as const,
    label: "GitHub",
    icon: Github,
    color: "bg-foreground/5 text-foreground border-foreground/10",
    hoverColor: "hover:border-foreground/30 hover:bg-foreground/5",
    placeholder: "https://github.com/yourname",
    benefit: "Projects, tech stack, contributions, open source work",
  },
  {
    key: "website" as const,
    label: "Portfolio / Website",
    icon: Globe,
    color: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
    hoverColor: "hover:border-teal-500/40 hover:bg-teal-500/5",
    placeholder: "https://yoursite.com",
    benefit: "Personal brand, case studies, additional context",
  },
  {
    key: "twitter" as const,
    label: "Twitter / X",
    icon: Twitter,
    color: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20",
    hoverColor: "hover:border-sky-500/40 hover:bg-sky-500/5",
    placeholder: "https://twitter.com/yourname",
    benefit: "Professional voice, industry engagement, thought leadership",
  },
] as const;

// ── Main Page ────────────────────────────────────────────────────────

export default function CareerNexusPage() {
  const { user, session } = useAuth();
  const token = session?.access_token ?? null;
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [completeness, setCompleteness] = useState<ProfileCompleteness | null>(null);
  const [resumeWorth, setResumeWorth] = useState<ResumeWorthScore | null>(null);
  const [aggregateGaps, setAggregateGaps] = useState<AggregateGapAnalysis | null>(null);
  const [marketIntel, setMarketIntel] = useState<any>(null);
  const [marketLoading, setMarketLoading] = useState(false);
  const [evidence, setEvidence] = useState<Record<string, any[]>>({});
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [activeTab, setActiveTab] = useState("profile");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Social links state (empty state)
  const [onboardingLinks, setOnboardingLinks] = useState<Record<string, string>>({});
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  // Live input values for social link fields (tracks what user has typed, even before save)
  const [socialInputs, setSocialInputs] = useState<Record<string, string>>({});

  useEffect(() => { if (token) api.setToken(token); }, [token]);

  const loadProfile = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const p = await api.profile.get();
      setProfile(p);
    } catch {
      setProfile(null);
    }
    setLoading(false);
  }, [token]);

  const loadIntelligence = useCallback(async () => {
    if (!token) return;
    try {
      const [comp, worth, gaps, ev, market] = await Promise.allSettled([
        api.profile.completeness(),
        api.profile.resumeWorth(),
        api.profile.aggregateGaps(),
        api.profile.syncedEvidence(),
        api.profile.marketIntelligence(),
      ]);
      if (comp.status === "fulfilled") setCompleteness(comp.value);
      if (worth.status === "fulfilled") setResumeWorth(worth.value);
      if (gaps.status === "fulfilled") setAggregateGaps(gaps.value);
      if (ev.status === "fulfilled") setEvidence(ev.value);
      if (market.status === "fulfilled" && !market.value?.error) setMarketIntel(market.value);
    } catch { /* non-critical */ }
  }, [token]);

  useEffect(() => { loadProfile(); }, [loadProfile]);
  useEffect(() => { if (profile) loadIntelligence(); }, [profile, loadIntelligence]);

  // Sync social input fields when profile loads/changes
  useEffect(() => {
    if (!profile) return;
    const links = profile.social_links || {};
    const ci = profile.contact_info || {};
    const inputs: Record<string, string> = {};
    for (const p of SOCIAL_PLATFORMS) {
      // Check social_links first
      const entry = (links as any)[p.key];
      if (entry) {
        inputs[p.key] = typeof entry === "string" ? entry : entry.url || "";
      }
      // Fallback to contact_info
      if (!inputs[p.key] && (ci as any)[p.key]) {
        inputs[p.key] = (ci as any)[p.key];
      }
    }
    setSocialInputs((prev) => {
      const merged = { ...inputs };
      for (const [k, v] of Object.entries(prev)) {
        if (v.trim()) merged[k] = v;
      }
      return merged;
    });
  }, [profile]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setErrorMessage(null);
    try {
      const p = await api.profile.upload(file, true);
      setProfile(p);
      // If user entered social links, save them alongside profile
      const hasLinks = Object.values(onboardingLinks).some((v) => v.trim());
      if (hasLinks) {
        try {
          await api.profile.updateSocialLinks(p.id, onboardingLinks);
          const updated = await api.profile.get();
          setProfile(updated);
        } catch { /* non-critical */ }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Upload failed. Please try again or use a different file format.");
    }
    setUploading(false);
    e.target.value = "";
  };

  const saveField = async (field: string, value: any) => {
    if (!profile) return;
    try {
      const updated = await api.profile.update({ id: profile.id, [field]: value });
      setProfile(updated);
      setEditingField(null);
    } catch (err: any) {
      setErrorMessage(err.message || "Update failed");
    }
  };

  const handleGenerateDocs = async () => {
    if (!profile) return;
    setGenerating(true);
    try {
      const docs = await api.profile.generateUniversalDocs(profile.id);
      setProfile({ ...profile, universal_documents: docs });
    } catch (err: any) {
      setErrorMessage(err.message || "Document generation failed");
    }
    setGenerating(false);
  };

  const handleReparse = async () => {
    if (!profile) return;
    setLoading(true);
    try {
      const p = await api.profile.reparse(profile.id);
      setProfile(p);
    } catch (err: any) {
      setErrorMessage(err.message || "Re-parse failed");
    }
    setLoading(false);
  };

  const saveSocialLinks = async (links: Record<string, string>) => {
    if (!profile) return;
    try {
      const updated = await api.profile.updateSocialLinks(profile.id, links);
      setProfile(updated);
    } catch { /* ignore */ }
  };

  const connectSocialProfile = async (platform: string, url: string) => {
    if (!profile || !url.trim()) return;
    setConnectingPlatform(platform);
    setErrorMessage(null);
    try {
      // Save URL first (in case it hasn't been saved via onBlur)
      const allUrls: Record<string, string> = {};
      for (const p of SOCIAL_PLATFORMS) {
        allUrls[p.key] = p.key === platform ? url : (socialInputs[p.key] || "");
      }
      await api.profile.updateSocialLinks(profile.id, allUrls);

      // Now connect and extract data
      await api.profile.connectSocial(profile.id, platform, url);

      // Reload profile to get updated social_links with extracted data
      const updated = await api.profile.getById(profile.id);
      if (updated) setProfile(updated);
    } catch (err: any) {
      setErrorMessage(err.message || `Failed to connect ${platform}`);
    }
    setConnectingPlatform(null);
  };

  // Hidden file input (shared across all upload triggers)
  const fileInput = <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={handleUpload} className="hidden" />;

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
      </div>
    );
  }

  // ── Empty State: Upload Resume to Get Started ────────────────────

  if (!profile) {
    return (
      <div className="space-y-6 animate-in fade-in duration-500">
        {fileInput}

        {/* Error Banner */}
        {errorMessage && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-rose-600 dark:text-rose-400">{errorMessage}</p>
              <p className="text-xs text-muted-foreground mt-1">Try a different file format (PDF, DOCX, TXT) or check that your file isn&apos;t image-based.</p>
            </div>
            <button onClick={() => setErrorMessage(null)} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Hero Card — empty state */}
        <div className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-teal-500 via-cyan-500 to-teal-600" />
          <div className="p-6 flex flex-col lg:flex-row gap-6">
            <div className="flex items-center gap-4 flex-1">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 text-white shrink-0 shadow-md shadow-teal-500/20">
                <Fingerprint className="h-8 w-8" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight">Career Nexus</h1>
                <p className="text-sm text-muted-foreground max-w-md">
                  Your career identity hub — upload your resume and we&apos;ll build your profile,
                  generate universal documents, and provide career intelligence.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Upload + Connect Side by Side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Upload Resume */}
          <Card className="rounded-2xl p-6">
            <h2 className="font-semibold mb-1">Upload Your Resume</h2>
            <p className="text-xs text-muted-foreground mb-4">
              Our AI parses it into structured sections — experience, skills, education, certifications.
            </p>
            <div className="rounded-xl border-2 border-dashed border-teal-500/30 bg-teal-500/5 p-6 text-center">
              <Upload className="mx-auto h-8 w-8 text-teal-500 mb-2" />
              <p className="text-sm font-medium mb-1">Drop your resume or click to browse</p>
              <p className="text-xs text-muted-foreground mb-3">PDF, DOCX, DOC, or TXT</p>
              <Button className="bg-gradient-to-r from-teal-500 to-cyan-600 text-white shadow-md shadow-teal-500/20" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                {uploading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Parsing...</> : <><Upload className="mr-2 h-4 w-4" /> Choose File</>}
              </Button>
            </div>
          </Card>

          {/* Connect Profiles */}
          <Card className="rounded-2xl p-6">
            <h2 className="font-semibold mb-1">Connect Your Profiles</h2>
            <p className="text-xs text-muted-foreground mb-4">
              We&apos;ll use these to enrich your data, find gaps, and improve your documents.
            </p>
            <div className="space-y-3">
              {SOCIAL_PLATFORMS.map((platform) => {
                const value = onboardingLinks[platform.key] || "";
                const isConnected = value.trim().length > 10;
                return (
                  <div key={platform.key} className="flex items-center gap-3">
                    <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border", platform.color)}>
                      <platform.icon className="h-4 w-4" />
                    </div>
                    <Input
                      value={value}
                      onChange={(e) => setOnboardingLinks({ ...onboardingLinks, [platform.key]: e.target.value })}
                      placeholder={platform.placeholder}
                      className={cn("text-sm h-9 rounded-lg flex-1", isConnected && "border-teal-500/30")}
                    />
                    {isConnected && <CheckCircle className="h-4 w-4 text-teal-500 shrink-0" />}
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Feature Preview — compact */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { icon: FileText, title: "Universal Resume", color: "text-blue-500 bg-blue-500/10" },
            { icon: BookOpen, title: "Full CV", color: "text-violet-500 bg-violet-500/10" },
            { icon: Fingerprint, title: "Personal Statement", color: "text-teal-500 bg-teal-500/10" },
            { icon: Code, title: "Portfolio", color: "text-amber-500 bg-amber-500/10" },
            { icon: Brain, title: "Intelligence", color: "text-rose-500 bg-rose-500/10" },
            { icon: TrendingUp, title: "Growth Roadmap", color: "text-emerald-500 bg-emerald-500/10" },
          ].map(({ icon: Ic, title, color }) => (
            <div key={title} className="flex flex-col items-center gap-2 rounded-xl border p-3 text-center">
              <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", color)}>
                <Ic className="h-4 w-4" />
              </div>
              <p className="text-[11px] font-medium text-muted-foreground">{title}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Profile Data ───────────────────────────────────────────────────

  const skills = profile.skills || [];
  const experience = profile.experience || [];
  const education = profile.education || [];
  const certs = profile.certifications || [];
  const projects = profile.projects || [];
  const languages = profile.languages || [];
  const social: Record<string, any> = (profile.social_links as any) || {};
  const contact: Record<string, any> = (profile.contact_info as any) || {};
  // Social connections data lives in contact_info.social_connections (always in DB)
  const socialConnections: Record<string, any> = contact.social_connections || {};
  const docs = profile.universal_documents || {};
  const docsStale = (profile.profile_version || 1) > (profile.universal_docs_version || 0);
  const score = completeness?.score ?? profile.completeness_score ?? 0;

  // Helper to get URL from social entry — checks social_links, then contact_info
  const getSocialUrl = (key: string): string => {
    const entry = social[key];
    if (entry) {
      if (typeof entry === "string") return entry;
      if (entry.url) return entry.url;
    }
    // Fallback: check contact_info (always in DB)
    return (contact as any)[key] || "";
  };
  const getSocialConnection = (key: string): any => {
    // Check social_links first (if nexus migration applied)
    const entry = social[key];
    if (entry && typeof entry !== "string" && entry.data) return entry;
    // Then check contact_info.social_connections (always works)
    return socialConnections[key] || null;
  };
  const getSocialData = (key: string): Record<string, any> | null => {
    const conn = getSocialConnection(key);
    return conn?.data || null;
  };
  const getSocialStatus = (key: string): string => {
    const conn = getSocialConnection(key);
    if (conn?.status) return conn.status;
    const url = getSocialUrl(key);
    return url.trim() ? "url_only" : "none";
  };

  const connectedPlatforms = SOCIAL_PLATFORMS.filter((p) => getSocialUrl(p.key).trim());
  const missingPlatforms = SOCIAL_PLATFORMS.filter((p) => !getSocialUrl(p.key).trim());

  const InlineField = ({ field, label, value, multiline = false }: { field: string; label: string; value: string; multiline?: boolean }) => {
    if (editingField === field) {
      return (
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{label}</label>
          {multiline ? (
            <Textarea defaultValue={value} onChange={(e) => setEditValue(e.target.value)} className="min-h-[80px]" autoFocus />
          ) : (
            <Input defaultValue={value} onChange={(e) => setEditValue(e.target.value)} autoFocus />
          )}
          <div className="flex gap-2">
            <Button size="sm" className="h-7 text-xs bg-teal-500 hover:bg-teal-600" onClick={() => saveField(field, editValue)}>Save</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingField(null)}>Cancel</Button>
          </div>
        </div>
      );
    }
    return (
      <div className="group">
        <label className="text-xs text-muted-foreground">{label}</label>
        <div className="flex items-start gap-2">
          <p className={cn("text-sm", !value && "text-muted-foreground italic")}>{value || "Not set"}</p>
          <button onClick={() => { setEditingField(field); setEditValue(value || ""); }} className="opacity-0 group-hover:opacity-100 transition-opacity">
            <Pencil className="h-3 w-3 text-muted-foreground hover:text-foreground" />
          </button>
        </div>
      </div>
    );
  };

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {fileInput}

      {/* Error Banner */}
      {errorMessage && (
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-rose-600 dark:text-rose-400">{errorMessage}</p>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Hero Card */}
      <div className="rounded-2xl border bg-card shadow-soft-sm overflow-hidden">
        {/* Accent bar */}
        <div className="h-1 bg-gradient-to-r from-teal-500 via-cyan-500 to-teal-600" />
        <div className="p-6">
          <div className="flex flex-col lg:flex-row lg:items-center gap-6">
            <div className="flex items-center gap-4 flex-1">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 text-white text-2xl font-bold shrink-0 shadow-md shadow-teal-500/20">
                {(profile.name || "?")[0].toUpperCase()}
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight">{profile.name || "Your Name"}</h1>
                <p className="text-sm text-muted-foreground">{profile.title || "Add your professional title"}</p>
                <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                  {contact.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{contact.location}</span>}
                  {contact.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{contact.email}</span>}
                </div>
              </div>
            </div>

            {/* Social connection icons */}
            <div className="flex items-center gap-2">
              {connectedPlatforms.map((platform) => (
                <a key={platform.key} href={getSocialUrl(platform.key)} target="_blank" rel="noopener noreferrer"
                  className={cn("flex h-9 w-9 items-center justify-center rounded-lg border transition-colors", platform.color)}>
                  <platform.icon className="h-4 w-4" />
                </a>
              ))}
              {missingPlatforms.length > 0 && (
                <button
                  onClick={() => setActiveTab("profile")}
                  className="flex h-9 items-center gap-1.5 rounded-lg border border-dashed border-muted-foreground/20 px-2.5 text-xs text-muted-foreground hover:border-teal-500/40 hover:text-teal-500 transition-colors"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Connect {missingPlatforms.length} more</span>
                </button>
              )}
            </div>

            {/* Stats */}
            <div className="flex items-center gap-6">
              <CompletionRing score={score} />
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div><span className="font-bold text-sm tabular-nums">{skills.length}</span> <span className="text-muted-foreground">Skills</span></div>
                <div><span className="font-bold text-sm tabular-nums">{experience.length}</span> <span className="text-muted-foreground">Roles</span></div>
                <div><span className="font-bold text-sm tabular-nums">{certs.length}</span> <span className="text-muted-foreground">Certs</span></div>
                <div><span className="font-bold text-sm tabular-nums">{projects.length}</span> <span className="text-muted-foreground">Projects</span></div>
              </div>
            </div>
          </div>

          {/* AI Improvement Suggestions */}
          {completeness && completeness.suggestions.length > 0 && (
            <div className="mt-4 rounded-xl bg-gradient-to-r from-teal-500/5 to-cyan-500/5 border border-teal-500/10 p-3">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="h-3.5 w-3.5 text-teal-500" />
                <span className="text-xs font-semibold text-teal-600 dark:text-teal-400">AI Suggestions to Boost Your Profile</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {completeness.suggestions.slice(0, 4).map((s, i) => (
                  <Badge key={i} variant="outline" className="text-[11px] border-teal-500/20 text-muted-foreground">{s}</Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid gap-1 bg-muted/50 p-1 rounded-xl">
          <TabsTrigger value="profile" className="gap-1.5 rounded-lg text-xs"><Fingerprint className="h-3.5 w-3.5" /><span className="hidden sm:inline">Profile</span></TabsTrigger>
          <TabsTrigger value="documents" className="gap-1.5 rounded-lg text-xs"><FileText className="h-3.5 w-3.5" /><span className="hidden sm:inline">Documents</span></TabsTrigger>
          <TabsTrigger value="intelligence" className="gap-1.5 rounded-lg text-xs"><Brain className="h-3.5 w-3.5" /><span className="hidden sm:inline">Intelligence</span></TabsTrigger>
          <TabsTrigger value="evidence" className="gap-1.5 rounded-lg text-xs"><ShieldCheck className="h-3.5 w-3.5" /><span className="hidden sm:inline">Evidence</span></TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5 rounded-lg text-xs"><Settings className="h-3.5 w-3.5" /><span className="hidden sm:inline">Settings</span></TabsTrigger>
        </TabsList>

        {/* ── TAB 1: Profile ─────────────────────────────────────────── */}
        <TabsContent value="profile" className="space-y-4">

          {/* Connections Section — Featured */}
          <AccordionSection title="Connected Profiles" icon={Link2} count={connectedPlatforms.length} defaultOpen={missingPlatforms.length > 0}
            badge={missingPlatforms.length > 0
              ? <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-500 ml-2">{missingPlatforms.length} not connected</Badge>
              : <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-500 ml-2">All connected</Badge>
            }
          >
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Connect your professional profiles so our AI can gather data to suggest improvements,
                enrich your documents, and identify skill gaps. The more connections, the smarter your career intelligence.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {SOCIAL_PLATFORMS.map((platform) => {
                  const savedUrl = getSocialUrl(platform.key);
                  const status = getSocialStatus(platform.key);
                  const data = getSocialData(platform.key);
                  const isConnecting = connectingPlatform === platform.key;
                  // Use live input value (what user has typed) — falls back to saved
                  const inputVal = socialInputs[platform.key] ?? savedUrl;
                  const hasInput = !!inputVal.trim();
                  const isFullyConnected = !!data;

                  return (
                    <div key={platform.key} className={cn(
                      "rounded-xl border p-3 transition-all duration-200",
                      isFullyConnected ? "border-emerald-500/20 bg-emerald-500/5" :
                      hasInput ? "border-teal-500/20 bg-teal-500/5" :
                      platform.hoverColor,
                    )}>
                      <div className="flex items-center gap-3 mb-2">
                        <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border", platform.color)}>
                          <platform.icon className="h-4 w-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-sm">{platform.label}</p>
                            {isConnecting ? (
                              <span className="flex items-center gap-1 text-[10px] text-primary font-medium">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Connecting...
                              </span>
                            ) : isFullyConnected ? (
                              <span className="flex items-center gap-1 text-[10px] text-emerald-500 font-medium">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                Connected
                              </span>
                            ) : null}
                          </div>
                          <p className="text-[10px] text-muted-foreground leading-tight">{platform.benefit}</p>
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <Input
                          value={inputVal}
                          placeholder={platform.placeholder}
                          className="text-sm h-8 rounded-lg flex-1"
                          onChange={(e) => setSocialInputs((prev) => ({ ...prev, [platform.key]: e.target.value }))}
                          onBlur={() => {
                            if (inputVal !== savedUrl && inputVal.trim()) {
                              const allUrls: Record<string, string> = {};
                              for (const p of SOCIAL_PLATFORMS) {
                                allUrls[p.key] = socialInputs[p.key] ?? getSocialUrl(p.key);
                              }
                              saveSocialLinks(allUrls);
                            }
                          }}
                        />
                        <Button
                          variant={isFullyConnected ? "outline" : "default"}
                          size="sm"
                          className={cn(
                            "h-8 px-3 rounded-lg text-xs shrink-0 transition-all",
                            !hasInput && "opacity-50 pointer-events-none",
                            isFullyConnected && "border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/10",
                          )}
                          disabled={!hasInput || isConnecting}
                          onClick={() => connectSocialProfile(platform.key, inputVal)}
                        >
                          {isConnecting ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : isFullyConnected ? (
                            <span className="flex items-center gap-1"><CheckCircle className="h-3 w-3" /> Synced</span>
                          ) : (
                            <span className="flex items-center gap-1"><Zap className="h-3 w-3" /> Connect</span>
                          )}
                        </Button>
                      </div>

                      {/* Connected data summary */}
                      {data && (
                        <div className="mt-2 animate-fade-up">
                          {/* GitHub summary */}
                          {platform.key === "github" && data.public_repos != null && (
                            <div className="text-[10px] text-muted-foreground bg-background/50 rounded-lg px-2.5 py-1.5 font-mono">
                              {data.public_repos} repos · {(data.top_languages || []).slice(0, 3).join(", ")} · {data.followers} followers
                            </div>
                          )}

                          {/* LinkedIn AI Analysis */}
                          {platform.key === "linkedin" && data.analysis && (
                            <details className="group">
                              <summary className="flex items-center gap-2 cursor-pointer text-[10px] text-emerald-500 font-medium bg-emerald-500/5 rounded-lg px-2.5 py-1.5 hover:bg-emerald-500/10 transition-colors">
                                <Brain className="h-3 w-3" />
                                LinkedIn Score: {data.analysis.overall_score}/100 — {data.analysis.priority_actions?.length || 0} actions recommended
                                <ChevronDown className="h-3 w-3 ml-auto transition-transform group-open:rotate-180" />
                              </summary>
                              <div className="mt-2 space-y-2.5 text-xs">
                                {/* Headlines */}
                                {data.analysis.headline_suggestions?.length > 0 && (
                                  <div className="rounded-lg border bg-card/50 p-3">
                                    <p className="font-medium text-2xs text-muted-foreground uppercase tracking-wider mb-1.5">Headline Suggestions</p>
                                    {data.analysis.headline_suggestions.map((h: string, j: number) => (
                                      <div key={j} className="flex items-start gap-2 py-1">
                                        <span className="text-2xs text-muted-foreground/50 font-mono mt-0.5">{j + 1}</span>
                                        <p className="text-sm flex-1">{h}</p>
                                        <button onClick={() => navigator.clipboard.writeText(h)} className="text-muted-foreground hover:text-foreground shrink-0">
                                          <ExternalLink className="h-3 w-3" />
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {/* Summary rewrite */}
                                {data.analysis.summary_rewrite && (
                                  <div className="rounded-lg border bg-card/50 p-3">
                                    <div className="flex items-center justify-between mb-1.5">
                                      <p className="font-medium text-2xs text-muted-foreground uppercase tracking-wider">Optimized About Section</p>
                                      <button
                                        onClick={() => navigator.clipboard.writeText(data.analysis.summary_rewrite)}
                                        className="text-2xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                                      >
                                        Copy
                                      </button>
                                    </div>
                                    <p className="text-xs text-muted-foreground whitespace-pre-line leading-relaxed">{data.analysis.summary_rewrite}</p>
                                  </div>
                                )}

                                {/* Skills to add */}
                                {data.analysis.skills_to_add?.length > 0 && (
                                  <div className="rounded-lg border bg-card/50 p-3">
                                    <p className="font-medium text-2xs text-muted-foreground uppercase tracking-wider mb-1.5">Skills to Add to LinkedIn</p>
                                    <div className="flex flex-wrap gap-1">
                                      {data.analysis.skills_to_add.map((s: string, j: number) => (
                                        <Badge key={j} variant="secondary" className="text-[10px]">{s}</Badge>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Priority actions */}
                                {data.analysis.priority_actions?.length > 0 && (
                                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                                    <p className="font-medium text-2xs text-amber-500 uppercase tracking-wider mb-1.5">Priority Actions</p>
                                    {data.analysis.priority_actions.map((a: string, j: number) => (
                                      <div key={j} className="flex items-start gap-2 py-0.5">
                                        <span className="text-amber-500 font-bold text-2xs mt-0.5">{j + 1}.</span>
                                        <p className="text-xs">{a}</p>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </details>
                          )}
                          {platform.key === "linkedin" && !data.analysis && (
                            <div className="text-[10px] text-muted-foreground bg-background/50 rounded-lg px-2.5 py-1.5 font-mono">
                              Profile linked — URL verified
                            </div>
                          )}

                          {/* Website summary */}
                          {platform.key === "website" && data.title && (
                            <div className="text-[10px] text-muted-foreground bg-background/50 rounded-lg px-2.5 py-1.5 font-mono">
                              {data.title}{data.keywords?.length ? ` · ${data.keywords.slice(0, 3).join(", ")}` : ""}
                            </div>
                          )}

                          {/* Twitter summary */}
                          {platform.key === "twitter" && data.handle && (
                            <div className="text-[10px] text-muted-foreground bg-background/50 rounded-lg px-2.5 py-1.5 font-mono">
                              @{data.handle} — profile linked
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* What we do with this data */}
              <div className="rounded-xl border border-dashed border-teal-500/20 bg-teal-500/5 p-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-500/10">
                    <Brain className="h-4 w-4 text-teal-500" />
                  </div>
                  <div>
                    <p className="font-medium text-sm mb-1">How we use your connections</p>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li className="flex items-start gap-1.5"><Zap className="h-3 w-3 text-teal-500 mt-0.5 shrink-0" />Cross-reference skills from LinkedIn with your resume to find gaps</li>
                      <li className="flex items-start gap-1.5"><Zap className="h-3 w-3 text-teal-500 mt-0.5 shrink-0" />Include GitHub projects and contributions in your portfolio</li>
                      <li className="flex items-start gap-1.5"><Zap className="h-3 w-3 text-teal-500 mt-0.5 shrink-0" />Suggest improvements based on industry peers with similar profiles</li>
                      <li className="flex items-start gap-1.5"><Zap className="h-3 w-3 text-teal-500 mt-0.5 shrink-0" />Auto-populate contact info and social proof in generated documents</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </AccordionSection>

          <AccordionSection title="Personal Information" icon={Fingerprint} defaultOpen>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <InlineField field="name" label="Full Name" value={profile.name || ""} />
              <InlineField field="title" label="Professional Title" value={profile.title || ""} />
              <div className="lg:col-span-2">
                <InlineField field="summary" label="Professional Summary" value={profile.summary || ""} multiline />
              </div>
            </div>
          </AccordionSection>

          <AccordionSection title="Work Experience" icon={Briefcase} count={experience.length}>
            <div className="space-y-3">
              {experience.map((exp, i) => (
                <div key={i} className="rounded-xl border p-3 hover:shadow-soft-sm transition-shadow">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-semibold text-sm">{exp.title}</p>
                      <p className="text-xs text-muted-foreground">{exp.company}{exp.location ? ` - ${exp.location}` : ""}</p>
                      <p className="text-xs text-teal-500">{exp.start_date} - {exp.is_current ? "Present" : exp.end_date || "N/A"}</p>
                    </div>
                  </div>
                  {exp.description && <p className="text-xs text-muted-foreground mt-2">{exp.description}</p>}
                  {exp.achievements && exp.achievements.length > 0 && (
                    <ul className="text-xs text-muted-foreground mt-1 space-y-0.5">
                      {exp.achievements.map((a, j) => <li key={j} className="flex gap-1"><span className="text-teal-500">-</span>{a}</li>)}
                    </ul>
                  )}
                  {exp.technologies && exp.technologies.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {exp.technologies.map((t, j) => <Badge key={j} variant="secondary" className="text-[10px] py-0">{t}</Badge>)}
                    </div>
                  )}
                </div>
              ))}
              {experience.length === 0 && (
                <div className="text-center py-6 text-sm text-muted-foreground">
                  <Briefcase className="mx-auto h-8 w-8 text-muted-foreground/20 mb-2" />
                  <p>No experience found. Upload a resume or connect your LinkedIn to auto-populate.</p>
                </div>
              )}
            </div>
          </AccordionSection>

          <AccordionSection title="Education" icon={GraduationCap} count={education.length}>
            <div className="space-y-3">
              {education.map((edu, i) => (
                <div key={i} className="rounded-xl border p-3">
                  <p className="font-semibold text-sm">{edu.degree}{edu.field ? ` in ${edu.field}` : ""}</p>
                  <p className="text-xs text-muted-foreground">{edu.institution}</p>
                  <p className="text-xs text-teal-500">{edu.start_date} - {edu.end_date || "Present"}</p>
                  {edu.gpa && <p className="text-xs text-muted-foreground mt-1">GPA: {edu.gpa}</p>}
                </div>
              ))}
              {education.length === 0 && <p className="text-sm text-muted-foreground italic text-center py-4">No education added yet.</p>}
            </div>
          </AccordionSection>

          <AccordionSection title="Skills" icon={Code} count={skills.length} defaultOpen>
            <div className="space-y-2">
              {skills.length > 0 ? (() => {
                // Group skills by category
                const groups: Record<string, typeof skills> = {};
                skills.forEach((s) => {
                  if (typeof s === "string") return;
                  const cat = s.category || "General";
                  if (!groups[cat]) groups[cat] = [];
                  groups[cat].push(s);
                });
                const sortedGroups = Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
                const levelColors = { expert: "bg-emerald-500", advanced: "bg-teal-500", intermediate: "bg-blue-500", beginner: "bg-muted-foreground/30" };
                const sourceColors = { resume: "bg-violet-500/10 text-violet-500", github: "bg-gray-500/10 text-gray-400", linkedin: "bg-blue-500/10 text-blue-500", manual: "bg-teal-500/10 text-teal-500" };
                const levelOrder = ["expert", "advanced", "intermediate", "beginner"];

                return sortedGroups.map(([cat, catSkills]) => {
                  const levelCounts = catSkills.reduce((acc, s) => {
                    if (typeof s !== "string") {
                      const lvl = (s.level || "intermediate").toLowerCase();
                      acc[lvl] = (acc[lvl] || 0) + 1;
                    }
                    return acc;
                  }, {} as Record<string, number>);

                  return (
                    <details key={cat} className="group rounded-xl border hover:border-teal-500/20 transition-colors">
                      <summary className="flex items-center gap-3 px-3 py-2.5 cursor-pointer list-none select-none">
                        <svg className="h-3.5 w-3.5 text-muted-foreground/40 transition-transform group-open:rotate-90 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                        </svg>
                        <span className="font-medium text-sm flex-1">{cat}</span>
                        <div className="flex items-center gap-1.5">
                          {levelOrder.map((lvl) => levelCounts[lvl] ? (
                            <span key={lvl} className="flex items-center gap-0.5 text-2xs text-muted-foreground">
                              <span className={cn("h-1.5 w-1.5 rounded-full", levelColors[lvl as keyof typeof levelColors])} />
                              {levelCounts[lvl]}
                            </span>
                          ) : null)}
                        </div>
                        <Badge variant="secondary" className="text-[10px] tabular-nums">{catSkills.length}</Badge>
                      </summary>
                      <div className="px-3 pb-3 pt-1 border-t border-border/50 space-y-1">
                        {catSkills.map((s, i) => {
                          if (typeof s === "string") return null;
                          const lvl = (s.level || "intermediate").toLowerCase();
                          const lvlIdx = levelOrder.indexOf(lvl);
                          const barWidth = lvlIdx >= 0 ? ((4 - lvlIdx) / 4) * 100 : 50;
                          const src = (s as any).source || "resume";
                          return (
                            <div key={i} className="flex items-center gap-3 py-1.5 rounded-lg px-2 hover:bg-muted/30 transition-colors">
                              <span className="text-sm font-medium flex-1 min-w-0 truncate">{s.name}</span>
                              <div className="w-16 h-1.5 bg-muted/20 rounded-full overflow-hidden shrink-0">
                                <div className={cn("h-full rounded-full", levelColors[lvl as keyof typeof levelColors] || "bg-blue-500")} style={{ width: `${barWidth}%` }} />
                              </div>
                              <span className="text-2xs text-muted-foreground w-10 text-right capitalize">{lvl}</span>
                              {s.years && <span className="text-2xs text-muted-foreground font-mono tabular-nums w-6 text-right">{s.years}y</span>}
                              <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full font-medium", sourceColors[src as keyof typeof sourceColors] || "bg-muted text-muted-foreground")}>{src}</span>
                            </div>
                          );
                        })}
                      </div>
                    </details>
                  );
                });
              })() : (
                <p className="text-sm text-muted-foreground italic py-2">No skills parsed yet. Upload a resume or connect GitHub.</p>
              )}
              {skills.length > 0 && !getSocialData("github") && (
                <div className="rounded-lg border border-dashed border-amber-500/20 bg-amber-500/5 p-2.5 flex items-center gap-2">
                  <Github className="h-4 w-4 text-amber-500 shrink-0" />
                  <p className="text-[11px] text-muted-foreground">Connect your GitHub to auto-detect additional technical skills from your repositories.</p>
                </div>
              )}
            </div>
          </AccordionSection>

          <AccordionSection title="Certifications" icon={Award} count={certs.length}>
            <div className="space-y-2">
              {certs.map((c, i) => (
                <div key={i} className="flex items-center justify-between rounded-xl border p-3">
                  <div>
                    <p className="font-semibold text-sm">{c.name}</p>
                    <p className="text-xs text-muted-foreground">{c.issuer}{c.date ? ` - ${c.date}` : ""}</p>
                  </div>
                  {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-teal-500" /></a>}
                </div>
              ))}
              {certs.length === 0 && (
                <div className="text-center py-4 text-sm text-muted-foreground">
                  <Award className="mx-auto h-8 w-8 text-muted-foreground/20 mb-2" />
                  <p>No certifications. Add them in the Evidence Vault or connect LinkedIn.</p>
                </div>
              )}
            </div>
          </AccordionSection>

          <AccordionSection title="Projects" icon={Code} count={projects.length}>
            <div className="space-y-2">
              {projects.map((p, i) => (
                <div key={i} className="rounded-xl border p-3">
                  <div className="flex items-start justify-between">
                    <p className="font-semibold text-sm">{p.name}</p>
                    {p.url && <a href={p.url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-teal-500" /></a>}
                  </div>
                  {p.description && <p className="text-xs text-muted-foreground mt-1">{p.description}</p>}
                  {p.technologies && p.technologies.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {p.technologies.map((t, j) => <Badge key={j} variant="secondary" className="text-[10px] py-0">{t}</Badge>)}
                    </div>
                  )}
                </div>
              ))}
              {projects.length === 0 && (
                <div className="text-center py-4 text-sm text-muted-foreground">
                  <Code className="mx-auto h-8 w-8 text-muted-foreground/20 mb-2" />
                  <p>No projects found. Connect GitHub or add them in the Evidence Vault.</p>
                </div>
              )}
            </div>
          </AccordionSection>

          {languages.length > 0 && (
            <AccordionSection title="Languages" icon={Globe} count={languages.length}>
              <div className="flex flex-wrap gap-2">
                {languages.map((l, i) => (
                  <Badge key={i} variant="outline" className="text-xs">
                    {typeof l === "string" ? l : `${l.language}${l.proficiency ? ` (${l.proficiency})` : ""}`}
                  </Badge>
                ))}
              </div>
            </AccordionSection>
          )}
        </TabsContent>

        {/* ── TAB 2: Documents ───────────────────────────────────────── */}
        <TabsContent value="documents" className="space-y-4">
          <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-4">
            <p className="font-semibold text-sm mb-2">Resume vs CV — What&apos;s the difference?</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-muted-foreground">
              <div>
                <p className="font-medium text-foreground">Resume</p>
                <p>1-2 pages, targeted, highlights relevant experience. Best for: industry jobs, most applications.</p>
              </div>
              <div>
                <p className="font-medium text-foreground">CV (Curriculum Vitae)</p>
                <p>Comprehensive, no page limit, includes all experience. Best for: academia, research, international roles.</p>
              </div>
            </div>
          </div>

          {(!docs.universal_resume_html || docsStale) && (
            <div className="flex items-center gap-3">
              <Button onClick={handleGenerateDocs} disabled={generating} className="bg-gradient-to-r from-teal-500 to-cyan-600 text-white shadow-md shadow-teal-500/20">
                {generating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</> : <><Sparkles className="mr-2 h-4 w-4" /> {docs.universal_resume_html ? "Regenerate Documents" : "Generate All Documents"}</>}
              </Button>
              {docsStale && docs.universal_resume_html && <Badge variant="outline" className="text-amber-500 border-amber-500/30">Profile updated — documents need refresh</Badge>}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { key: "universal_resume_html" as const, title: "Universal Resume", desc: "Professional 1-2 page resume for any application", icon: FileText, docType: "resume" },
              { key: "full_cv_html" as const, title: "Full CV", desc: "Comprehensive career record — no page limits", icon: BookOpen, docType: "cv" },
              { key: "personal_statement_html" as const, title: "Personal Statement", desc: "Your career narrative and professional mission", icon: Fingerprint, docType: "personalStatement" },
              { key: "portfolio_html" as const, title: "Portfolio Showcase", desc: "Projects & certifications as mini case studies", icon: Code, docType: "portfolio" },
            ].map(({ key, title, desc, icon: Ic, docType }) => {
              const html = docs[key];
              const hasDoc = !!html;
              return (
                <Card key={key} className="rounded-2xl p-4 hover:shadow-soft-md transition-shadow">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/10">
                        <Ic className="h-4 w-4 text-teal-500" />
                      </div>
                      <div>
                        <p className="font-semibold text-sm">{title}</p>
                        <p className="text-xs text-muted-foreground">{desc}</p>
                      </div>
                    </div>
                    <Badge variant={hasDoc ? (docsStale ? "outline" : "secondary") : "outline"} className={cn("text-[10px]", hasDoc && !docsStale && "text-emerald-500 border-emerald-500/30", docsStale && hasDoc && "text-amber-500 border-amber-500/30")}>
                      {hasDoc ? (docsStale ? "Needs Update" : "Ready") : "Not Generated"}
                    </Badge>
                  </div>
                  {hasDoc && (
                    <div className="flex gap-2">
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button size="sm" variant="outline" className="h-7 text-xs gap-1">
                            <Eye className="h-3 w-3" /> Preview
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
                          <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
                          <PaperContainer html={html} title={title} documentType={docType} />
                        </DialogContent>
                      </Dialog>
                      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => {
                        exportToPdf(sanitizeHtml(html), { documentType: "cv", filename: title });
                      }}>
                        <Download className="h-3 w-3" /> Export
                      </Button>
                    </div>
                  )}
                  {!hasDoc && <p className="text-xs text-muted-foreground italic">Click &quot;Generate All Documents&quot; above.</p>}
                </Card>
              );
            })}
          </div>
        </TabsContent>

        {/* ── TAB 3: Intelligence ─────────────────────────────────────── */}
        <TabsContent value="intelligence" className="space-y-6">

          {/* ── Hero stats row ──────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: "Resume Worth", value: resumeWorth ? `${resumeWorth.score}` : "—", sub: resumeWorth?.label || "Upload resume", icon: Target, color: "text-teal-500", bg: "bg-teal-500/10" },
              { label: "Total Skills", value: `${skills.length}`, sub: skills.length > 0 ? `${new Set(skills.filter(s => typeof s !== "string").map(s => s.category || "General")).size} categories` : "None yet", icon: Code, color: "text-violet-500", bg: "bg-violet-500/10" },
              { label: "Applications", value: `${aggregateGaps?.total_applications_analyzed ?? 0}`, sub: "Analyzed for gaps", icon: Briefcase, color: "text-blue-500", bg: "bg-blue-500/10" },
              { label: "Completeness", value: `${score}%`, sub: score >= 80 ? "Looking great" : score >= 50 ? "Getting there" : "Keep going", icon: Target, color: "text-amber-500", bg: "bg-amber-500/10" },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl border bg-card/50 p-4 hover:shadow-soft-sm transition-shadow">
                <div className="flex items-center gap-2 mb-2">
                  <div className={cn("flex h-7 w-7 items-center justify-center rounded-lg", stat.bg)}>
                    <stat.icon className={cn("h-3.5 w-3.5", stat.color)} />
                  </div>
                  <span className="text-2xs text-muted-foreground uppercase tracking-wider">{stat.label}</span>
                </div>
                <p className="text-2xl font-bold tabular-nums">{stat.value}</p>
                <p className="text-2xs text-muted-foreground mt-0.5">{stat.sub}</p>
              </div>
            ))}
          </div>

          {/* ── Resume Worth + Skills Breakdown ────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Resume Worth Gauge — wider */}
            <Card className="rounded-2xl p-6 lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <Target className="h-4 w-4 text-teal-500" /> Resume Worth
                </h3>
                {resumeWorth && (
                  <Badge variant="outline" className={cn("text-[10px]",
                    resumeWorth.score >= 85 ? "border-emerald-500/30 text-emerald-500" :
                    resumeWorth.score >= 65 ? "border-teal-500/30 text-teal-500" :
                    resumeWorth.score >= 40 ? "border-amber-500/30 text-amber-500" :
                    "border-rose-500/30 text-rose-500"
                  )}>{resumeWorth.label}</Badge>
                )}
              </div>
              {resumeWorth ? (
                <>
                  <ResumeWorthGauge data={resumeWorth} />
                  {/* Breakdown bars */}
                  <div className="mt-5 space-y-2.5">
                    {Object.entries(resumeWorth.breakdown).map(([key, val]) => {
                      const v = val as number;
                      return (
                        <div key={key}>
                          <div className="flex items-center justify-between text-2xs mb-1">
                            <span className="text-muted-foreground capitalize">{key.replace(/_/g, " ")}</span>
                            <span className="font-medium tabular-nums">{v}/100</span>
                          </div>
                          <div className="h-1.5 bg-muted/20 rounded-full overflow-hidden">
                            <div
                              className={cn("h-full rounded-full transition-all duration-700",
                                v >= 80 ? "bg-emerald-500" : v >= 50 ? "bg-teal-500" : v >= 25 ? "bg-amber-500" : "bg-rose-500"
                              )}
                              style={{ width: `${v}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="py-8 text-center">
                  <Target className="mx-auto h-10 w-10 text-muted-foreground/15 mb-3" />
                  <p className="text-sm text-muted-foreground">Complete your profile to see your score</p>
                  <p className="text-2xs text-muted-foreground mt-1">Add skills, experience, and connect profiles.</p>
                </div>
              )}
            </Card>

            {/* Skills Breakdown — wider */}
            <Card className="rounded-2xl p-6 lg:col-span-3">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-violet-500" /> Skills Breakdown
                </h3>
                {skills.length > 0 && (
                  <span className="text-2xs text-muted-foreground">{skills.length} total skills</span>
                )}
              </div>
              {skills.length > 0 ? (
                <div className="space-y-3">
                  {(() => {
                    const categories: Record<string, { count: number; levels: Record<string, number> }> = {};
                    skills.forEach((s) => {
                      if (typeof s !== "string") {
                        const cat = s.category || "General";
                        if (!categories[cat]) categories[cat] = { count: 0, levels: {} };
                        categories[cat].count += 1;
                        const lvl = (s.level || "intermediate").toLowerCase();
                        categories[cat].levels[lvl] = (categories[cat].levels[lvl] || 0) + 1;
                      }
                    });
                    const entries = Object.entries(categories).sort((a, b) => b[1].count - a[1].count).slice(0, 8);
                    const max = Math.max(...entries.map(([, v]) => v.count), 1);
                    const barColors = ["from-teal-500 to-cyan-500", "from-violet-500 to-indigo-500", "from-blue-500 to-cyan-500", "from-amber-500 to-orange-500", "from-emerald-500 to-teal-500", "from-rose-500 to-pink-500", "from-sky-500 to-blue-500", "from-fuchsia-500 to-violet-500"];
                    return entries.map(([cat, { count, levels }], i) => (
                      <div key={cat} className="group">
                        <div className="flex items-center gap-3">
                          <span className="w-28 text-right text-xs text-muted-foreground truncate group-hover:text-foreground transition-colors">{cat}</span>
                          <div className="flex-1 h-5 bg-muted/15 rounded-lg overflow-hidden relative">
                            <div className={cn("h-full rounded-lg bg-gradient-to-r transition-all duration-700", barColors[i % barColors.length])} style={{ width: `${(count / max) * 100}%` }} />
                            {/* Level breakdown dots inside the bar */}
                            <div className="absolute inset-y-0 right-2 flex items-center gap-1">
                              {levels.expert ? <span className="text-[8px] text-white/70 font-mono">{levels.expert}E</span> : null}
                              {levels.advanced ? <span className="text-[8px] text-white/70 font-mono">{levels.advanced}A</span> : null}
                            </div>
                          </div>
                          <span className="w-8 text-right font-semibold text-xs tabular-nums">{count}</span>
                        </div>
                      </div>
                    ));
                  })()}
                  {/* Skill level legend */}
                  <div className="flex items-center gap-4 pt-2 border-t border-border/50 mt-2">
                    <span className="text-2xs text-muted-foreground">Levels:</span>
                    {["expert", "advanced", "intermediate", "beginner"].map((level) => {
                      const count = skills.filter(s => typeof s !== "string" && (s.level || "intermediate").toLowerCase() === level).length;
                      if (count === 0) return null;
                      return (
                        <span key={level} className="flex items-center gap-1 text-2xs">
                          <span className={cn("h-2 w-2 rounded-full",
                            level === "expert" ? "bg-emerald-500" : level === "advanced" ? "bg-teal-500" : level === "intermediate" ? "bg-blue-500" : "bg-muted-foreground/30"
                          )} />
                          <span className="text-muted-foreground capitalize">{level}</span>
                          <span className="font-medium tabular-nums">{count}</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <Code className="mx-auto h-10 w-10 text-muted-foreground/15 mb-3" />
                  <p className="text-sm text-muted-foreground">No skills data yet</p>
                  <p className="text-2xs text-muted-foreground mt-1">Upload a resume or connect GitHub to populate skills.</p>
                </div>
              )}
            </Card>
          </div>

          {/* ── Market Intelligence ────────────────────────────────── */}
          {marketIntel && (
            <div className="space-y-4">
              {/* Market Overview */}
              <Card className="rounded-2xl overflow-hidden">
                <div className={cn("px-6 py-4 border-b border-border/50 bg-gradient-to-r to-transparent",
                  marketIntel.market_overview?.temperature === "hot" ? "from-emerald-500/10" :
                  marketIntel.market_overview?.temperature === "warm" ? "from-amber-500/10" :
                  marketIntel.market_overview?.temperature === "cool" ? "from-blue-500/10" :
                  "from-gray-500/10"
                )}>
                  <div className="flex items-center gap-3">
                    <TrendingUp className="h-5 w-5 text-teal-500" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">Market Intelligence</h3>
                        <Badge variant="outline" className={cn("text-[10px]",
                          marketIntel.market_overview?.temperature === "hot" ? "border-emerald-500/30 text-emerald-500" :
                          marketIntel.market_overview?.temperature === "warm" ? "border-amber-500/30 text-amber-500" :
                          marketIntel.market_overview?.temperature === "cool" ? "border-blue-500/30 text-blue-500" :
                          "border-gray-500/30 text-gray-500"
                        )}>
                          {marketIntel.market_overview?.temperature || "analyzing"} market
                        </Badge>
                      </div>
                      <p className="text-2xs text-muted-foreground">{marketIntel.market_overview?.location}</p>
                    </div>
                    <Button
                      variant="ghost" size="sm" className="text-2xs gap-1"
                      disabled={marketLoading}
                      onClick={async () => {
                        setMarketLoading(true);
                        try {
                          const data = await api.profile.marketIntelligence(true);
                          if (!data.error) setMarketIntel(data);
                        } catch {}
                        setMarketLoading(false);
                      }}
                    >
                      <RefreshCw className={cn("h-3 w-3", marketLoading && "animate-spin")} />
                      Refresh
                    </Button>
                  </div>
                  {marketIntel.market_overview?.summary && (
                    <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{marketIntel.market_overview.summary}</p>
                  )}
                </div>

                <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Skills Demand */}
                  {marketIntel.skills_demand?.length > 0 && (
                    <div>
                      <p className="font-medium text-xs mb-2">Skills in Demand</p>
                      <div className="space-y-1.5">
                        {marketIntel.skills_demand.slice(0, 8).map((s: any, i: number) => (
                          <div key={i} className="flex items-center gap-2 text-xs">
                            <span className="font-medium flex-1 truncate">{s.skill}</span>
                            <span className={cn("text-2xs",
                              s.trend === "rising" ? "text-emerald-500" : s.trend === "declining" ? "text-rose-500" : "text-muted-foreground"
                            )}>
                              {s.trend === "rising" ? "↑" : s.trend === "declining" ? "↓" : "→"}
                            </span>
                            <Badge variant="outline" className={cn("text-[9px]",
                              s.demand_level === "high" ? "border-emerald-500/30 text-emerald-500" :
                              s.demand_level === "medium" ? "border-amber-500/30 text-amber-500" :
                              "border-gray-500/30 text-gray-500"
                            )}>{s.demand_level}</Badge>
                            {s.salary_premium && <span className="text-emerald-500 text-2xs font-mono">{s.salary_premium}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Salary Insights */}
                  {marketIntel.salary_insights?.range_median > 0 && (
                    <div>
                      <p className="font-medium text-xs mb-2">Salary Range</p>
                      <div className="space-y-2">
                        <div className="relative h-3 bg-muted/20 rounded-full overflow-hidden">
                          <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-blue-500 via-teal-500 to-emerald-500" style={{ width: "100%" }} />
                        </div>
                        <div className="flex justify-between text-2xs text-muted-foreground font-mono">
                          <span>{marketIntel.salary_insights.currency} {marketIntel.salary_insights.range_low?.toLocaleString()}</span>
                          <span className="font-semibold text-foreground">{marketIntel.salary_insights.currency} {marketIntel.salary_insights.range_median?.toLocaleString()}</span>
                          <span>{marketIntel.salary_insights.currency} {marketIntel.salary_insights.range_high?.toLocaleString()}</span>
                        </div>
                      </div>

                      {/* Opportunity Suggestions */}
                      {marketIntel.opportunity_suggestions?.length > 0 && (
                        <div className="mt-3">
                          <p className="font-medium text-xs mb-1.5">Suggested Roles</p>
                          {marketIntel.opportunity_suggestions.slice(0, 3).map((o: any, i: number) => (
                            <div key={i} className="rounded-lg border bg-card/50 p-2 mb-1.5 text-xs">
                              <div className="flex items-center justify-between">
                                <span className="font-medium">{o.title}</span>
                                <span className="text-2xs text-muted-foreground font-mono">{o.estimated_salary}</span>
                              </div>
                              <p className="text-2xs text-muted-foreground mt-0.5">{o.match_reason}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Skill gaps to market */}
                {marketIntel.skill_gaps_to_market?.length > 0 && (
                  <div className="px-4 pb-4">
                    <p className="font-medium text-xs mb-2">Market Skill Gaps</p>
                    <div className="flex flex-wrap gap-1.5">
                      {marketIntel.skill_gaps_to_market.map((g: any, i: number) => (
                        <span key={i} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] border",
                          g.urgency === "high" ? "border-rose-500/20 bg-rose-500/5 text-rose-500" :
                          g.urgency === "medium" ? "border-amber-500/20 bg-amber-500/5 text-amber-500" :
                          "border-blue-500/20 bg-blue-500/5 text-blue-500"
                        )}>
                          {g.skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {marketIntel.from_cache && (
                  <div className="px-4 pb-3">
                    <p className="text-[10px] text-muted-foreground/50">Cached data · Click Refresh for latest analysis</p>
                  </div>
                )}
              </Card>
            </div>
          )}

          {/* ── Gap Analysis ────────────────────────────────────────── */}
          {aggregateGaps && aggregateGaps.total_applications_analyzed > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Missing Skills */}
              <Card className="rounded-2xl overflow-hidden">
                <div className="bg-gradient-to-r from-amber-500/10 to-transparent px-6 py-4 border-b border-border/50">
                  <h3 className="font-semibold flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 text-amber-500" /> Skill Gaps
                  </h3>
                  <p className="text-2xs text-muted-foreground mt-0.5">Most requested skills you&apos;re missing across {aggregateGaps.total_applications_analyzed} applications</p>
                </div>
                <div className="p-4 space-y-1">
                  {aggregateGaps.most_missing_skills.slice(0, 8).map((item, i) => (
                    <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted/30 transition-colors group">
                      <span className="text-2xs text-muted-foreground/50 font-mono w-4 tabular-nums">{i + 1}</span>
                      <span className="flex-1 font-medium text-sm">{item.skill}</span>
                      <Badge variant="outline" className={cn("text-[10px] border-0",
                        item.avg_severity === "high" ? "bg-rose-500/10 text-rose-500" :
                        item.avg_severity === "medium" ? "bg-amber-500/10 text-amber-500" :
                        "bg-blue-500/10 text-blue-500"
                      )}>
                        {item.avg_severity}
                      </Badge>
                      <span className="text-2xs text-muted-foreground tabular-nums font-mono">{item.frequency}x</span>
                    </div>
                  ))}
                  {aggregateGaps.most_missing_skills.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No gaps detected yet</p>
                  )}
                </div>
              </Card>

              {/* Strongest Areas */}
              <Card className="rounded-2xl overflow-hidden">
                <div className="bg-gradient-to-r from-emerald-500/10 to-transparent px-6 py-4 border-b border-border/50">
                  <h3 className="font-semibold flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-emerald-500" /> Strengths
                  </h3>
                  <p className="text-2xs text-muted-foreground mt-0.5">Your most recognized skills across applications</p>
                </div>
                <div className="p-4 space-y-1">
                  {aggregateGaps.strongest_areas.slice(0, 8).map((item, i) => (
                    <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted/30 transition-colors">
                      <span className="text-2xs text-muted-foreground/50 font-mono w-4 tabular-nums">{i + 1}</span>
                      <span className="flex-1 font-medium text-sm">{item.area}</span>
                      <div className="flex items-center gap-1.5">
                        {Array.from({ length: Math.min(item.frequency, 5) }).map((_, j) => (
                          <span key={j} className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        ))}
                        <span className="text-2xs text-muted-foreground tabular-nums font-mono ml-1">{item.frequency}x</span>
                      </div>
                    </div>
                  ))}
                  {aggregateGaps.strongest_areas.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">Apply to more jobs to see patterns</p>
                  )}
                </div>
              </Card>
            </div>
          )}

          {/* ── Growth Roadmap ──────────────────────────────────────── */}
          {aggregateGaps && aggregateGaps.recommended_learning.length > 0 && (
            <Card className="rounded-2xl overflow-hidden">
              <div className="bg-gradient-to-r from-teal-500/10 to-transparent px-6 py-4 border-b border-border/50">
                <h3 className="font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-teal-500" /> Growth Roadmap
                </h3>
                <p className="text-2xs text-muted-foreground mt-0.5">Priority skills to learn based on demand across your target roles</p>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {aggregateGaps.recommended_learning.map((item, i) => {
                    const pct = Math.round((item.appears_in_jobs / Math.max(item.total_jobs, 1)) * 100);
                    return (
                      <div key={i} className="rounded-xl border bg-card/50 p-3.5 hover:shadow-soft-sm hover:border-teal-500/20 transition-all group">
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <span className="font-semibold text-sm group-hover:text-teal-500 transition-colors">{item.skill}</span>
                          <Badge variant={item.priority === "high" ? "destructive" : "secondary"} className="text-[10px] shrink-0">{item.priority}</Badge>
                        </div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <div className="flex-1 h-1.5 bg-muted/20 rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-teal-500 to-cyan-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-2xs font-mono tabular-nums text-muted-foreground">{pct}%</span>
                        </div>
                        <p className="text-2xs text-muted-foreground">Needed in {item.appears_in_jobs} of {item.total_jobs} target jobs</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </Card>
          )}

          {/* ── Empty state ─────────────────────────────────────────── */}
          {(!aggregateGaps || aggregateGaps.total_applications_analyzed === 0) && (
            <div className="rounded-2xl border border-dashed border-teal-500/20 bg-gradient-to-br from-teal-500/5 to-transparent p-10 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-500/10 mx-auto mb-4">
                <Brain className="h-7 w-7 text-teal-500" />
              </div>
              <p className="font-semibold text-base">Career Intelligence Gets Smarter Over Time</p>
              <p className="text-xs text-muted-foreground mt-2 max-w-md mx-auto leading-relaxed">
                As you create applications for different jobs, we analyze skill gaps across all of them.
                You&apos;ll see which skills are most in-demand, your strongest areas, and a personalized growth roadmap.
              </p>
              <Button variant="outline" size="sm" className="mt-5 gap-2 rounded-xl" onClick={() => window.location.href = "/new"}>
                <Plus className="h-3.5 w-3.5" /> Create Your First Application
              </Button>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 4: Evidence ─────────────────────────────────────────── */}
        <TabsContent value="evidence" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold">Evidence Vault Mirror</h3>
              <p className="text-xs text-muted-foreground">Certifications and projects from your Evidence Vault, mapped to your profile.</p>
            </div>
            <Button variant="outline" size="sm" className="text-xs gap-2" onClick={() => window.location.href = "/evidence"}>
              <ShieldCheck className="h-3.5 w-3.5" /> Open Evidence Vault
            </Button>
          </div>

          {Object.entries(evidence).map(([type, items]) => {
            if (!items || items.length === 0) return null;
            return (
              <div key={type}>
                <h4 className="font-medium text-sm capitalize mb-2">{type}</h4>
                <div className="space-y-2">
                  {items.map((item: any, i: number) => (
                    <div key={i} className="rounded-xl border p-3 flex items-center justify-between hover:shadow-soft-sm transition-shadow">
                      <div>
                        <p className="font-medium text-sm">{item.title}</p>
                        <p className="text-xs text-muted-foreground">{item.description?.slice(0, 100)}</p>
                        {item.skills && item.skills.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {item.skills.slice(0, 5).map((s: string, j: number) => (
                              <Badge key={j} variant="secondary" className="text-[10px] py-0">{s}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      <Badge variant="outline" className="text-[10px] text-teal-500 border-teal-500/30">Synced</Badge>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {Object.values(evidence).every((v) => !v || v.length === 0) && (
            <div className="rounded-2xl border border-dashed p-8 text-center">
              <ShieldCheck className="mx-auto h-10 w-10 text-muted-foreground/20 mb-3" />
              <p className="font-medium text-sm">No Evidence Items Synced</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                Add certifications, projects, and courses in the Evidence Vault. They&apos;ll appear here
                and strengthen your career documents.
              </p>
              <Button variant="outline" size="sm" className="mt-4 gap-2" onClick={() => window.location.href = "/evidence"}>
                <Plus className="h-3.5 w-3.5" /> Add Evidence
              </Button>
            </div>
          )}
        </TabsContent>

        {/* ── TAB 5: Settings ─────────────────────────────────────────── */}
        <TabsContent value="settings" className="space-y-4">
          <Card className="rounded-2xl p-6 space-y-4">
            <h3 className="font-semibold">Profile Settings</h3>

            <div className="flex items-center justify-between rounded-xl border p-4 hover:bg-muted/20 transition-colors">
              <div>
                <p className="font-medium text-sm">Re-parse Resume</p>
                <p className="text-xs text-muted-foreground">Re-analyze your uploaded resume with AI to extract updated data.</p>
              </div>
              <Button variant="outline" size="sm" onClick={handleReparse} disabled={loading}>
                <RefreshCw className="mr-2 h-3.5 w-3.5" /> Re-parse
              </Button>
            </div>

            <div className="flex items-center justify-between rounded-xl border p-4 hover:bg-muted/20 transition-colors">
              <div>
                <p className="font-medium text-sm">Upload New Resume</p>
                <p className="text-xs text-muted-foreground">Replace your current resume with a new version.</p>
              </div>
              <Button variant="outline" size="sm" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                <Upload className="mr-2 h-3.5 w-3.5" /> Upload
              </Button>
            </div>

            <div className="flex items-center justify-between rounded-xl border p-4 hover:bg-muted/20 transition-colors">
              <div>
                <p className="font-medium text-sm">Export Profile Data</p>
                <p className="text-xs text-muted-foreground">Download your complete profile as JSON.</p>
              </div>
              <Button variant="outline" size="sm" onClick={() => {
                const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a"); a.href = url; a.download = "career-nexus-profile.json"; a.click();
                URL.revokeObjectURL(url);
              }}>
                <Download className="mr-2 h-3.5 w-3.5" /> Export JSON
              </Button>
            </div>

            <Separator />

            <div className="flex items-center justify-between rounded-xl border border-destructive/20 p-4">
              <div>
                <p className="font-medium text-sm text-destructive">Delete Profile</p>
                <p className="text-xs text-muted-foreground">Permanently remove your profile and all associated data. Cannot be undone.</p>
              </div>
              <Button variant="destructive" size="sm" onClick={async () => {
                if (confirm("Are you sure you want to delete your profile? This cannot be undone.")) {
                  await api.profile.delete(profile.id);
                  setProfile(null);
                }
              }}>
                <Trash2 className="mr-2 h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
