import type { Metadata } from "next";
import Link from "next/link";
import { MarketingShell } from "@/components/marketing-shell";
import { BookOpen, FileText, Target, Brain, TrendingUp, Shield } from "lucide-react";

export const metadata: Metadata = {
  title: "Resources — Career guides, ATS playbooks, interview prep",
  description:
    "Free career intelligence. The exact frameworks, templates, and playbooks our AI uses — broken down for humans.",
  alternates: { canonical: "/resources" },
};

const GUIDES = [
  {
    icon: FileText,
    tag: "Résumé",
    title: "The 2026 ATS-proof résumé checklist",
    read: "8 min read",
    summary: "The exact 32-point checklist our Sentinel agent runs on every résumé. Print it. Apply it. Get through the screen.",
    href: "/resources/ats-checklist",
  },
  {
    icon: Target,
    tag: "Strategy",
    title: "Evidence mapping: turning claims into proof",
    read: "6 min read",
    summary: "Why recruiters trust GitHub links and cert numbers over adjectives — and how to rewrite every line of your résumé around proof.",
    href: "/resources/evidence-mapping",
  },
  {
    icon: Brain,
    tag: "Interviews",
    title: "The STAR method, but actually useful",
    read: "9 min read",
    summary: "Most STAR guides give you a template. We give you a scoring rubric so you can self-grade your own answers.",
    href: "/resources/star-method",
  },
  {
    icon: TrendingUp,
    tag: "Job search",
    title: "How to apply to 20 roles a week without burning out",
    read: "5 min read",
    summary: "The weekly cadence, batching system, and tooling stack high-performing job seekers use.",
    href: "/resources/high-volume-search",
  },
  {
    icon: Shield,
    tag: "Privacy",
    title: "What AI job tools do with your data (the ugly truth)",
    read: "7 min read",
    summary: "We audited 14 competitors. Here's who trains on your résumé, who sells it, and what to look for before uploading.",
    href: "/resources/ai-data-audit",
  },
  {
    icon: BookOpen,
    tag: "Salary",
    title: "The negotiation script that raised our users' offers 14% on average",
    read: "11 min read",
    summary: "Exact language for the counter-offer email, the phone call, and the final handshake.",
    href: "/resources/negotiation-script",
  },
];

export default function ResourcesPage() {
  return (
    <MarketingShell
      kicker={<><BookOpen className="h-3.5 w-3.5" /> Free resources</>}
      title="Career intelligence, in plain English"
      description="The exact frameworks, templates, and playbooks our AI uses — free for everyone."
    >
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {GUIDES.map((g, i) => (
          <Link
            key={i}
            href={g.href}
            className="group rounded-2xl border bg-card p-6 hover:shadow-soft-md hover:-translate-y-0.5 transition-all"
          >
            <div className="flex items-center justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary group-hover:bg-primary group-hover:text-white transition-colors">
                <g.icon className="h-5 w-5" />
              </div>
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {g.tag}
              </span>
            </div>
            <h3 className="mt-4 text-base font-semibold leading-tight">{g.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{g.summary}</p>
            <p className="mt-4 text-xs text-muted-foreground">{g.read} · Read →</p>
          </Link>
        ))}
      </div>
    </MarketingShell>
  );
}
