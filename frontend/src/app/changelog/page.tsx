import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing-shell";
import { Rocket, CheckCircle2 } from "lucide-react";

export const metadata: Metadata = {
  title: "Changelog — What's new in HireStack AI",
  description: "Shipping updates every week. See what's changed and what's next.",
  alternates: { canonical: "/changelog" },
};

const RELEASES = [
  {
    date: "April 2026",
    version: "v4.4",
    title: "Interview Simulator, rebuilt",
    items: [
      "Five-agent swarm for question generation (interviewer, coach, adversary, judge, editor).",
      "Deterministic fallback so simulator never blocks — even when a model provider is down.",
      "Per-answer STAR scoring (situation / task / action / result, 0–25 each).",
      "Difficulty and skills now influence every question.",
    ],
  },
  {
    date: "April 2026",
    version: "v4.3",
    title: "Mobile UX overhaul",
    items: [
      "Bottom tab navigation with haptic feedback on supported devices.",
      "Sticky CTAs on marketing pages and full-bleed dashboard layouts.",
      "Playwright visual audit suite to catch regressions before they ship.",
    ],
  },
  {
    date: "March 2026",
    version: "v4.2",
    title: "Company Intelligence v2",
    items: [
      "Live news and tech-stack signals from 140+ sources.",
      "Glassdoor-style culture fingerprint (inferred, never scraped).",
      "Automatic weaving of company keywords into cover letters.",
    ],
  },
  {
    date: "March 2026",
    version: "v4.1",
    title: "ATS Scanner v3",
    items: [
      "Keyword-density heatmap.",
      "Format compatibility check against Workday, Greenhouse, Lever, SAP SuccessFactors.",
      "Concrete fix suggestions with one-click apply.",
    ],
  },
  {
    date: "February 2026",
    version: "v4.0",
    title: "Six-agent pipeline",
    items: [
      "Recon, Atlas, Cipher, Quill, Sentinel, and Conductor launched.",
      "Real-time event streaming replaced polling.",
      "Workspace persistence across tabs and devices.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <MarketingShell
      kicker={<><Rocket className="h-3.5 w-3.5" /> Changelog</>}
      title="Shipping updates every week"
      description="We believe a changelog is a promise. Here's what we've delivered."
    >
      <div className="mx-auto max-w-3xl space-y-10">
        {RELEASES.map((r, i) => (
          <article key={i} className="rounded-2xl border bg-card p-6">
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">{r.title}</h2>
                <p className="mt-1 text-xs text-muted-foreground">{r.date}</p>
              </div>
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
                {r.version}
              </span>
            </div>
            <ul className="mt-5 space-y-2.5">
              {r.items.map((it, j) => (
                <li key={j} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  <span className="leading-relaxed text-foreground/90">{it}</span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </MarketingShell>
  );
}
