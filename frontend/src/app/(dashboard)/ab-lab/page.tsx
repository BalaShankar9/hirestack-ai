"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { DocVariant } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FlaskConical, Loader2, Check, ArrowLeftRight, Star, ClipboardCopy, Sparkles, Target, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "@/hooks/use-toast";

type VariantComparisonRow = {
  variant: string;
  tone: string;
  ats_score?: number;
  readability_score?: number;
  evidence_coverage?: number;
  composite_score?: number;
  delta_vs_original?: { ats_score?: number; readability_score?: number; evidence_coverage?: number };
};

type ComparisonResponse = {
  comparison?: VariantComparisonRow[];
  winner?: { variant: string; composite_score?: number; reasoning?: string; weights?: Record<string, number> } | null;
  weights?: Record<string, number>;
  summary?: string;
};

function DeltaArrow({ value }: { value?: number }) {
  if (value === undefined || value === null) return null;
  if (Math.abs(value) < 0.5) return <Minus className="h-3 w-3 text-muted-foreground" aria-label="unchanged" />;
  if (value > 0) return <TrendingUp className="h-3 w-3 text-emerald-500" aria-label={`+${value}`} />;
  return <TrendingDown className="h-3 w-3 text-rose-500" aria-label={`${value}`} />;
}

const TONE_CONFIG = {
  conservative: { label: "Conservative", color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400", desc: "Formal, traditional approach" },
  balanced: { label: "Balanced", color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400", desc: "Professional middle ground" },
  creative: { label: "Creative", color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400", desc: "Bold, innovative style" },
};

export default function ABLabPage() {
  const { user } = useAuth();
  const userId = user?.uid || user?.id || null;
  const [applicationId, setApplicationId] = useState("");
  const [documentContent, setDocumentContent] = useState("");
  const [documentType, setDocumentType] = useState("cv");
  const [jobTitle, setJobTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [variants, setVariants] = useState<DocVariant[]>([]);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const generateVariants = async () => {
    if (!documentContent.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.variants.generate({
        original_content: documentContent,
        document_type: documentType,
        job_title: jobTitle || undefined,
        application_id: applicationId || undefined,
      });
      setVariants(result.variants || []);
      setComparison(result.comparison);
      setSelectedId(null);
    } catch (e: any) {
      setError(e.message || "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  const selectVariant = async (id: string) => {
    try {
      await api.variants.select(id);
      setSelectedId(id);
    } catch (e: any) {
      setError(e.message || "Selection failed");
    }
  };

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-fuchsia-500/10">
          <FlaskConical className="h-5 w-5 text-fuchsia-600 dark:text-fuchsia-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Compare Versions</h1>
          <p className="text-xs text-muted-foreground">Paste a document and get 3 tone variants (conservative, balanced, creative) to compare side by side</p>
        </div>
      </div>

      {/* Input */}
      <div className="rounded-2xl border p-4 sm:p-6 space-y-4 shadow-soft-sm hover:shadow-soft-md transition-all duration-300">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
          <h2 className="text-lg font-semibold">Source Document</h2>
          <p className="text-xs text-muted-foreground">You&apos;ll get 3 versions: conservative, balanced, and creative</p>
        </div>
        <div className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="ab-doc-content" className="text-sm font-medium">Document Content *</label>
            <Textarea
              id="ab-doc-content"
              className="h-32 font-mono resize-none"
              placeholder="Paste your CV/resume/cover letter content here..."
              value={documentContent}
              onChange={(e) => setDocumentContent(e.target.value)}
              maxLength={5000}
            />
            <div className="flex justify-end text-[11px] text-muted-foreground mt-1">
              {documentContent.length.toLocaleString()}/5,000
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <label htmlFor="ab-doc-type" className="text-sm font-medium">Document Type</label>
              <Select value={documentType} onValueChange={setDocumentType}>
                <SelectTrigger id="ab-doc-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cv">CV / Resume</SelectItem>
                  <SelectItem value="cover_letter">Cover Letter</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label htmlFor="ab-job-title" className="text-sm font-medium">Job Title</label>
              <Input id="ab-job-title" placeholder="e.g. Senior Engineer" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label htmlFor="ab-app-id" className="text-sm font-medium">Application ID (optional)</label>
              <Input id="ab-app-id" placeholder="UUID" value={applicationId} onChange={(e) => setApplicationId(e.target.value)} />
            </div>
          </div>
        </div>
        <Button onClick={generateVariants} disabled={loading || !documentContent.trim()} size="lg" className="w-full">
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FlaskConical className="h-4 w-4 mr-2" />}
          {loading ? "Generating 3 Variants..." : "Generate Variants"}
        </Button>
      </div>

      {error && <p className="text-destructive text-sm bg-destructive/10 p-3 rounded-lg">{error}</p>}

      {/* Variants Grid */}
      {variants.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center gap-2">
            <ArrowLeftRight className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-xl font-semibold">Compare Variants</h2>
          </div>

          {/* System-recommended winner banner — ADR-0016 */}
          {comparison?.winner?.variant && (
            <div className="rounded-2xl border-2 border-amber-500/40 bg-gradient-to-r from-amber-500/5 to-yellow-500/5 p-4 sm:p-5 flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15">
                <Sparkles className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">System recommends:</h3>
                  <span className="px-2.5 py-0.5 rounded-lg text-xs font-medium bg-amber-500/15 text-amber-700 dark:text-amber-300">
                    {(TONE_CONFIG[comparison.winner.variant as keyof typeof TONE_CONFIG]?.label) || comparison.winner.variant}
                  </span>
                  {typeof comparison.winner.composite_score === "number" && (
                    <span className="text-[11px] text-muted-foreground">composite {comparison.winner.composite_score.toFixed(1)}/100</span>
                  )}
                </div>
                {comparison.winner.reasoning && (
                  <p className="text-sm text-muted-foreground leading-relaxed">{comparison.winner.reasoning}</p>
                )}
                <p className="text-[11px] text-muted-foreground/80">
                  You can still pick any variant manually below — your selection always overrides the recommendation.
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {variants.map((v) => {
              const tone = TONE_CONFIG[v.tone as keyof typeof TONE_CONFIG] || TONE_CONFIG.balanced;
              const isSelected = selectedId === v.id;
              const compRow = comparison?.comparison?.find((c) => c.variant === v.tone);
              const isSystemWinner = comparison?.winner?.variant === v.tone;

              return (
                <div
                  key={v.id}
                  className={`rounded-2xl border-2 p-6 space-y-4 shadow-soft-sm hover:shadow-soft-md transition-all duration-300 ${
                    isSelected ? "border-primary shadow-lg" : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`px-3 py-1 rounded-lg text-[11px] font-medium ${tone.color}`}>
                      {tone.label}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {isSystemWinner && (
                        <span
                          className="flex items-center gap-1 text-amber-600 dark:text-amber-400 text-[11px] font-medium"
                          title="System-recommended winner"
                        >
                          <Sparkles className="h-3.5 w-3.5" /> Recommended
                        </span>
                      )}
                      {isSelected && (
                        <span className="flex items-center gap-1 text-primary text-sm font-medium">
                          <Star className="h-4 w-4 fill-primary" /> Selected
                        </span>
                      )}
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground">{tone.desc}</p>

                  {/* Scores — ATS, Readability, Evidence Coverage */}
                  <div className="grid grid-cols-3 gap-2">
                    {(compRow?.ats_score ?? v.ats_score) !== undefined && (
                      <div className="text-center p-2 rounded-lg bg-muted/30">
                        <div className="text-[11px] text-muted-foreground">ATS</div>
                        <div className="font-bold text-lg">{compRow?.ats_score ?? v.ats_score}</div>
                        {compRow?.delta_vs_original?.ats_score !== undefined && (
                          <div className="flex items-center justify-center gap-0.5 text-[10px] text-muted-foreground">
                            <DeltaArrow value={compRow.delta_vs_original.ats_score} />
                            <span>{compRow.delta_vs_original.ats_score > 0 ? "+" : ""}{compRow.delta_vs_original.ats_score}</span>
                          </div>
                        )}
                      </div>
                    )}
                    {(compRow?.readability_score ?? v.readability_score) !== undefined && (
                      <div className="text-center p-2 rounded-lg bg-muted/30">
                        <div className="text-[11px] text-muted-foreground">Readability</div>
                        <div className="font-bold text-lg">{compRow?.readability_score ?? v.readability_score}</div>
                        {compRow?.delta_vs_original?.readability_score !== undefined && (
                          <div className="flex items-center justify-center gap-0.5 text-[10px] text-muted-foreground">
                            <DeltaArrow value={compRow.delta_vs_original.readability_score} />
                            <span>{compRow.delta_vs_original.readability_score > 0 ? "+" : ""}{compRow.delta_vs_original.readability_score}</span>
                          </div>
                        )}
                      </div>
                    )}
                    {compRow?.evidence_coverage !== undefined && (
                      <div
                        className="text-center p-2 rounded-lg bg-emerald-500/10"
                        title="Percent of job-title keywords this variant covers (proxy for evidence-graph coverage)"
                      >
                        <div className="text-[11px] text-emerald-700 dark:text-emerald-400 flex items-center justify-center gap-1">
                          <Target className="h-3 w-3" /> Evidence
                        </div>
                        <div className="font-bold text-lg">{compRow.evidence_coverage}</div>
                        {compRow.delta_vs_original?.evidence_coverage !== undefined && (
                          <div className="flex items-center justify-center gap-0.5 text-[10px] text-muted-foreground">
                            <DeltaArrow value={compRow.delta_vs_original.evidence_coverage} />
                            <span>{compRow.delta_vs_original.evidence_coverage > 0 ? "+" : ""}{compRow.delta_vs_original.evidence_coverage}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Content Preview */}
                  <div className="rounded-lg bg-muted/30 p-3 max-h-48 overflow-y-auto">
                    <p className="text-xs font-mono whitespace-pre-wrap">
                      {typeof v.content === "string" ? v.content.slice(0, 500) : JSON.stringify(v.content, null, 2).slice(0, 500)}
                      {(typeof v.content === "string" ? v.content.length : JSON.stringify(v.content).length) > 500 && "..."}
                    </p>
                  </div>

                  {/* Diff Summary */}
                  {(v as any).diff_summary && (
                    <div className="text-xs text-muted-foreground bg-muted/20 rounded-lg p-2">
                      {(v as any).diff_summary}
                    </div>
                  )}

                  <Button
                    onClick={() => selectVariant(v.id)}
                    variant={isSelected ? "default" : "outline"}
                    className="w-full"
                    disabled={isSelected}
                  >
                    {isSelected ? <Check className="h-4 w-4 mr-2" /> : null}
                    {isSelected ? "Winner" : "Select This Variant"}
                  </Button>

                  {isSelected && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full gap-1.5"
                      onClick={() => {
                        const text = typeof v.content === "string" ? v.content : JSON.stringify(v.content, null, 2);
                        navigator.clipboard.writeText(text);
                        toast({ title: "Copied!", description: "Variant content copied to clipboard." });
                      }}
                    >
                      <ClipboardCopy className="h-3.5 w-3.5" />
                      Copy Content
                    </Button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Composite-score breakdown — only shown when we have new-format data */}
          {comparison?.weights && comparison.comparison && comparison.comparison.length > 0 && (
            <div className="rounded-2xl border p-5 shadow-soft-sm space-y-3">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <h3 className="font-semibold text-sm">Composite scoring</h3>
                <p className="text-[11px] text-muted-foreground">
                  Weights: Evidence {Math.round((comparison.weights.evidence_coverage ?? 0) * 100)}% · ATS {Math.round((comparison.weights.ats_score ?? 0) * 100)}% · Readability {Math.round((comparison.weights.readability_score ?? 0) * 100)}%
                </p>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {comparison.comparison.map((row) => {
                  const t = TONE_CONFIG[row.variant as keyof typeof TONE_CONFIG];
                  const isWin = comparison.winner?.variant === row.variant;
                  return (
                    <div
                      key={row.variant}
                      className={`rounded-lg p-3 text-center ${isWin ? "bg-amber-500/10 border border-amber-500/30" : "bg-muted/30"}`}
                    >
                      <div className="text-[11px] text-muted-foreground">{t?.label || row.variant}</div>
                      <div className="text-2xl font-bold">{row.composite_score?.toFixed(1) ?? "—"}</div>
                      <div className="text-[10px] text-muted-foreground">/ 100</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Cross-link: apply the best variant */}
          <div className="rounded-2xl border border-dashed bg-card/50 p-4 flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              <strong className="text-foreground">Like a variant?</strong>{" "}
              Use it in a full application workspace.
            </p>
            <Link href="/new">
              <Button size="sm" variant="outline" className="rounded-xl shrink-0 gap-1.5">
                <ArrowLeftRight className="h-3.5 w-3.5" /> New Application
              </Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
