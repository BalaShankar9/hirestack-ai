"use client";

import { useState } from "react";
import { MarketingShell } from "@/components/marketing-shell";
import { api } from "@/lib/api";
import { AlertTriangle, AlertOctagon, Info, Sparkles, ShieldCheck } from "lucide-react";

/**
 * Public JD anti-pattern checker (E3.frontend) — paste a job
 * description, get a categorized report of bias, vagueness, urgency,
 * and unrealistic-experience flags.
 *
 * Wraps POST /api/jd-check (E3.api commit 678194b). Anonymous + rate
 * limited (10/min). No persistence — output is deterministic, so we
 * don't need a permalink scheme like /ghost-check.
 */

type Severity = "critical" | "warn" | "info";

interface Finding {
  category: string;
  severity: Severity;
  snippet: string;
  term: string;
  char_start: number;
  char_end: number;
}

interface Report {
  findings: Finding[];
  by_category: Record<string, number>;
  severity_counts: Record<Severity, number>;
  total_count: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  ageist: "Ageist language",
  gendered: "Gendered language",
  vague_compensation: "Vague compensation",
  unrealistic_experience: "Unrealistic experience",
  culture_red_flag: "Culture red flag",
  urgency: "Urgency pressure",
};

const SEVERITY_STYLE: Record<Severity, { badge: string; icon: typeof AlertTriangle }> = {
  critical: {
    badge: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
    icon: AlertOctagon,
  },
  warn: {
    badge: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20",
    icon: AlertTriangle,
  },
  info: {
    badge: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/20",
    icon: Info,
  },
};

const MAX_INPUT_BYTES = 200 * 1024; // mirrors backend _MAX_JD_BYTES

export default function JdCheckPage() {
  const [text, setText] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const oversize = text.length > MAX_INPUT_BYTES;
  const empty = text.trim().length === 0;

  const handleScan = async () => {
    if (empty || oversize || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = (await api.jdCheck.scan(text)) as Report;
      setReport(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed. Try again in a moment.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setText("");
    setReport(null);
    setError(null);
  };

  return (
    <MarketingShell
      kicker={<><Sparkles className="h-3.5 w-3.5" /> JD Check · free · no signup</>}
      title="Is this job description a red flag?"
      description="Paste any job description. We surface ageist, gendered, vague-comp, unrealistic-experience, culture, and urgency patterns instantly. No signup. Nothing stored."
    >
      <div className="grid gap-6 lg:grid-cols-5">
        {/* Input column */}
        <div className="lg:col-span-3 flex flex-col gap-3">
          <label htmlFor="jd-text" className="text-sm font-semibold">
            Paste the job description
          </label>
          <textarea
            id="jd-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Hire a rockstar engineer..."
            rows={18}
            className="w-full rounded-xl border bg-background p-4 font-mono text-sm leading-relaxed shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            aria-invalid={oversize}
            aria-describedby="jd-meta"
          />
          <div id="jd-meta" className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {text.length.toLocaleString()} / {MAX_INPUT_BYTES.toLocaleString()} chars
            </span>
            {oversize && (
              <span className="text-red-600 dark:text-red-400 font-medium">
                Too long — trim to under 200KB.
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleScan}
              disabled={empty || oversize || loading}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground btn-glow hover:shadow-glow-md transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Scanning…" : "Scan this JD"}
            </button>
            <button
              type="button"
              onClick={handleClear}
              disabled={loading || (empty && !report)}
              className="inline-flex items-center gap-2 rounded-xl border bg-background px-5 py-2.5 text-sm font-semibold hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Clear
            </button>
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
        </div>

        {/* Report column */}
        <div className="lg:col-span-2">
          {report ? <ReportPanel report={report} /> : <EmptyPanel />}
        </div>
      </div>
    </MarketingShell>
  );
}

function EmptyPanel() {
  return (
    <div className="rounded-xl border bg-card/40 p-6 text-sm text-muted-foreground">
      <ShieldCheck className="h-5 w-5 mb-3 text-primary" />
      <p className="font-medium text-foreground">What we look for</p>
      <ul className="mt-2 list-disc pl-5 space-y-1">
        <li>Ageist phrasing (&ldquo;digital native&rdquo;, &ldquo;recent grads only&rdquo;)</li>
        <li>Gendered words (&ldquo;rockstar&rdquo;, &ldquo;ninja&rdquo;, &ldquo;guru&rdquo;)</li>
        <li>Vague compensation (&ldquo;competitive&rdquo;, &ldquo;DOE&rdquo;)</li>
        <li>Unrealistic experience (15+ years on a 10-year-old tech)</li>
        <li>Culture red flags (&ldquo;we&rsquo;re a family&rdquo;)</li>
        <li>Urgency pressure (&ldquo;ASAP&rdquo;, &ldquo;immediate start&rdquo;)</li>
      </ul>
    </div>
  );
}

function ReportPanel({ report }: { report: Report }) {
  if (report.total_count === 0) {
    return (
      <div className="rounded-xl border bg-emerald-500/5 p-6">
        <ShieldCheck className="h-6 w-6 text-emerald-600 dark:text-emerald-400 mb-3" />
        <h2 className="text-lg font-bold">No red flags found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This JD passes our anti-pattern checks. That doesn&rsquo;t guarantee a
          great employer — just that the language is clean.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card/60 p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-2xl font-bold">{report.total_count}</h2>
          <span className="text-xs uppercase tracking-wider text-muted-foreground">
            findings
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["critical", "warn", "info"] as Severity[]).map((sev) => {
            const count = report.severity_counts[sev] ?? 0;
            if (count === 0) return null;
            const style = SEVERITY_STYLE[sev];
            const Icon = style.icon;
            return (
              <span
                key={sev}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.badge}`}
              >
                <Icon className="h-3.5 w-3.5" />
                {count} {sev}
              </span>
            );
          })}
        </div>
      </div>

      <ul className="space-y-3" aria-label="findings list">
        {report.findings.map((f, i) => {
          const style = SEVERITY_STYLE[f.severity];
          const Icon = style.icon;
          return (
            <li key={`${f.category}-${f.char_start}-${i}`} className="rounded-xl border bg-card/40 p-4">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${style.badge}`}
                >
                  <Icon className="h-3 w-3" />
                  {f.severity}
                </span>
                <span className="text-xs text-muted-foreground">
                  {CATEGORY_LABELS[f.category] ?? f.category}
                </span>
              </div>
              <p className="mt-2 text-sm font-mono">
                <span className="rounded bg-amber-500/15 px-1 py-0.5 font-semibold">
                  {f.term}
                </span>
              </p>
              <p className="mt-1.5 text-xs text-muted-foreground italic">
                &ldquo;{f.snippet}&rdquo;
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
