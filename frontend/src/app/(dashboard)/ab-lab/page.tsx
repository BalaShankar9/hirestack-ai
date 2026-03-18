"use client";

import React, { useState } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { DocVariant } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FlaskConical, Loader2, Check, ArrowLeftRight, Star, ClipboardCopy } from "lucide-react";
import { toast } from "@/hooks/use-toast";

const TONE_CONFIG = {
  conservative: { label: "Conservative", color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300", desc: "Formal, traditional approach" },
  balanced: { label: "Balanced", color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300", desc: "Professional middle ground" },
  creative: { label: "Creative", color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300", desc: "Bold, innovative style" },
};

export default function ABLabPage() {
  const { user } = useAuth();
  const [applicationId, setApplicationId] = useState("");
  const [documentContent, setDocumentContent] = useState("");
  const [documentType, setDocumentType] = useState("cv");
  const [jobTitle, setJobTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [variants, setVariants] = useState<DocVariant[]>([]);
  const [comparison, setComparison] = useState<any>(null);
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
        <FlaskConical className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">A/B Document Lab</h1>
          <p className="text-muted-foreground">Generate 3 tone variants and pick the winner</p>
        </div>
      </div>

      {/* Input */}
      <div className="rounded-xl border p-6 space-y-4">
        <h2 className="text-lg font-semibold">Source Document</h2>
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

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {variants.map((v) => {
              const tone = TONE_CONFIG[v.tone as keyof typeof TONE_CONFIG] || TONE_CONFIG.balanced;
              const isSelected = selectedId === v.id;

              return (
                <div
                  key={v.id}
                  className={`rounded-xl border-2 p-6 space-y-4 transition-all ${
                    isSelected ? "border-primary shadow-lg" : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${tone.color}`}>
                      {tone.label}
                    </span>
                    {isSelected && (
                      <span className="flex items-center gap-1 text-primary text-sm font-medium">
                        <Star className="h-4 w-4 fill-primary" /> Selected
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-muted-foreground">{tone.desc}</p>

                  {/* Scores */}
                  <div className="grid grid-cols-2 gap-2">
                    {v.ats_score !== undefined && (
                      <div className="text-center p-2 rounded-lg bg-muted/30">
                        <div className="text-xs text-muted-foreground">ATS</div>
                        <div className="font-bold text-lg">{v.ats_score}</div>
                      </div>
                    )}
                    {v.readability_score !== undefined && (
                      <div className="text-center p-2 rounded-lg bg-muted/30">
                        <div className="text-xs text-muted-foreground">Readability</div>
                        <div className="font-bold text-lg">{v.readability_score}</div>
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

          {/* Comparison Summary */}
          {comparison && (
            <div className="rounded-xl border p-6">
              <h3 className="font-semibold text-lg mb-3">🔬 AI Comparison</h3>
              <p className="text-sm text-muted-foreground">{comparison.summary || JSON.stringify(comparison)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
