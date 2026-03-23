"use client";

import React, { useState } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import type { ATSScan } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScanSearch, CheckCircle, XCircle, AlertTriangle, Loader2 } from "lucide-react";
import { toast } from "@/hooks/use-toast";

export default function ATSScannerPage() {
  const { user } = useAuth();
  const [documentContent, setDocumentContent] = useState("");
  const [jdText, setJdText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [scan, setScan] = useState<ATSScan | null>(null);
  const [error, setError] = useState("");

  const runScan = async () => {
    if (!documentContent.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.ats.scan({
        document_content: documentContent,
        document_type: "cv",
        job_title: jobTitle,
        company,
        jd_text: jdText,
      });
      setScan(result);
      toast({ title: "Scan complete", description: `ATS score: ${result.ats_score ?? "N/A"}. Check results below.`, variant: "success" });
    } catch (e: any) {
      setError(e.message || "Scan failed");
    } finally {
      setLoading(false);
    }
  };

  const passIcon = scan?.pass_prediction === "pass"
    ? <CheckCircle className="h-8 w-8 text-green-500" />
    : scan?.pass_prediction === "fail"
    ? <XCircle className="h-8 w-8 text-red-500" />
    : <AlertTriangle className="h-8 w-8 text-yellow-500" />;

  return (
    <div className="space-y-8 p-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3">
        <ScanSearch className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Recruiter Lens — ATS Scanner</h1>
          <p className="text-muted-foreground">See your document through an ATS system&apos;s eyes</p>
        </div>
      </div>

      {/* Input Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <label htmlFor="ats-document" className="text-sm font-medium">Your Document (CV/Resume HTML or text)</label>
          <Textarea
            id="ats-document"
            className="h-48 font-mono resize-none"
            placeholder="Paste your CV/resume content here..."
            value={documentContent}
            onChange={(e) => setDocumentContent(e.target.value)}
            maxLength={5000}
          />
          <div className="flex justify-end text-[11px] text-muted-foreground mt-1">
            {documentContent.length.toLocaleString()}/5,000
          </div>
        </div>
        <div className="space-y-4">
          <label htmlFor="ats-jd" className="text-sm font-medium">Job Description</label>
          <Textarea
            id="ats-jd"
            className="h-48 resize-none"
            placeholder="Paste the target job description..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            maxLength={5000}
          />
          <div className="flex justify-end text-[11px] text-muted-foreground mt-1">
            {jdText.length.toLocaleString()}/5,000
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input
          id="ats-job-title"
          placeholder="Job Title"
          value={jobTitle}
          onChange={(e) => setJobTitle(e.target.value)}
        />
        <Input
          id="ats-company"
          placeholder="Company"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
        />
      </div>

      <Button onClick={runScan} disabled={loading || !documentContent.trim()} size="lg" className="w-full">
        {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <ScanSearch className="h-4 w-4 mr-2" />}
        {loading ? "Scanning..." : "Run ATS Scan"}
      </Button>

      {error && <p className="text-destructive text-sm">{error}</p>}

      {/* Results */}
      {scan && (
        <div className="space-y-6">
          {/* Score Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <ScoreCard label="ATS Score" value={scan.ats_score} icon={passIcon} />
            <ScoreCard label="Keywords" value={scan.keyword_match_rate} suffix="%" />
            <ScoreCard label="Readability" value={scan.readability_score} />
            <ScoreCard label="Formatting" value={scan.format_score} />
            <ScoreCard
              label="Prediction"
              value={scan.pass_prediction?.toUpperCase()}
              color={scan.pass_prediction === "pass" ? "text-green-600" : scan.pass_prediction === "fail" ? "text-red-600" : "text-yellow-600"}
            />
          </div>

          {/* Matched Keywords */}
          <div className="rounded-xl border p-6">
            <h3 className="font-semibold text-lg mb-3 text-green-600">✅ Matched Keywords ({scan.matched_keywords?.length || 0})</h3>
            <div className="flex flex-wrap gap-2">
              {scan.matched_keywords?.map((k, i) => (
                <span key={i} className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full text-sm">
                  {k.keyword} <span className="text-xs opacity-70">×{k.frequency}</span>
                </span>
              ))}
            </div>
          </div>

          {/* Missing Keywords */}
          <div className="rounded-xl border p-6">
            <h3 className="font-semibold text-lg mb-3 text-red-600">❌ Missing Keywords ({scan.missing_keywords?.length || 0})</h3>
            <div className="space-y-2">
              {scan.missing_keywords?.map((k, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    k.importance === "critical" ? "bg-red-100 text-red-700" : "bg-yellow-100 text-yellow-700"
                  }`}>
                    {k.importance}
                  </span>
                  <span className="font-medium">{k.keyword}</span>
                  <span className="text-sm text-muted-foreground">— {k.suggestion}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recommendations */}
          <div className="rounded-xl border p-6">
            <h3 className="font-semibold text-lg mb-3">🎯 Recommendations</h3>
            <div className="space-y-3">
              {scan.recommendations?.map((r, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
                    {r.priority}
                  </span>
                  <div>
                    <span className={`text-xs px-2 py-0.5 rounded mr-2 ${
                      r.impact === "high" ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
                    }`}>
                      {r.impact} impact
                    </span>
                    <span className="text-sm">{r.action}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ScoreCard({
  label,
  value,
  suffix = "",
  icon,
  color,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  icon?: React.ReactNode;
  color?: string;
}) {
  const numVal = typeof value === "number" ? value : 0;
  const scoreColor = color || (typeof value === "number"
    ? numVal >= 80 ? "text-green-600" : numVal >= 60 ? "text-yellow-600" : "text-red-600"
    : "");

  return (
    <div className="rounded-xl border p-4 text-center">
      {icon && <div className="flex justify-center mb-2">{icon}</div>}
      <div className={`text-2xl font-bold ${scoreColor}`}>
        {value}{suffix}
      </div>
      <div className="text-xs text-muted-foreground mt-1">{label}</div>
    </div>
  );
}
