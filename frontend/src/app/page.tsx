"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight, Target, Sparkles, TrendingUp, Zap, Shield, BarChart3,
  CheckCircle2, FileText, Brain, Search, Users, Star, Globe,
} from "lucide-react";

const FEATURES = [
  {
    icon: <Brain className="h-5 w-5" />,
    gradient: "from-primary/10 to-violet-500/10",
    iconColor: "text-primary",
    title: "AI-Powered Analysis",
    description: "Multiple AI agents analyze the job description, research the company, and map your experience to every requirement — so nothing gets missed.",
  },
  {
    icon: <Target className="h-5 w-5" />,
    gradient: "from-emerald-500/10 to-teal-500/10",
    iconColor: "text-emerald-600",
    title: "Company Intelligence",
    description: "Before writing a single word, the system researches the company — culture, tech stack, recent news — and weaves it into your application.",
  },
  {
    icon: <BarChart3 className="h-5 w-5" />,
    gradient: "from-blue-500/10 to-cyan-500/10",
    iconColor: "text-blue-600",
    title: "ATS Compatibility Check",
    description: "See your resume through the recruiter's ATS. Keyword match scoring, format analysis, and concrete fix suggestions.",
  },
  {
    icon: <Shield className="h-5 w-5" />,
    gradient: "from-amber-500/10 to-orange-500/10",
    iconColor: "text-amber-600",
    title: "Evidence-Backed Claims",
    description: "Attach certifications, projects, and metrics to your claims. Most candidates submit claims — you submit proof.",
  },
  {
    icon: <TrendingUp className="h-5 w-5" />,
    gradient: "from-rose-500/10 to-pink-500/10",
    iconColor: "text-rose-600",
    title: "Gap Analysis & Improvement",
    description: "See exactly what you're missing vs the ideal candidate. Get actionable steps to close every gap before you apply.",
  },
  {
    icon: <FileText className="h-5 w-5" />,
    gradient: "from-violet-500/10 to-purple-500/10",
    iconColor: "text-violet-600",
    title: "35+ Document Types",
    description: "CV, cover letter, personal statement, portfolio, plus job-specific documents. Academic roles get research statements. Legal gets writing samples.",
  },
];

const STEPS = [
  { n: "1", title: "Paste the job description", desc: "Drop in any JD — our AI extracts every requirement, keyword, and hidden expectation.", icon: Search },
  { n: "2", title: "Upload your resume", desc: "PDF, DOCX, or plain text. We parse layout-aware with ligature repair and section detection.", icon: FileText },
  { n: "3", title: "Watch agents work", desc: "6 AI agents collaborate in real-time — you see every step as they build your application.", icon: Brain },
  { n: "4", title: "Download & apply", desc: "Get ATS-optimized documents ready to submit. Tailored to the exact role and company.", icon: Zap },
];

const STATS = [
  { value: "35+", label: "document types" },
  { value: "6", label: "AI analysis steps" },
  { value: "Complete", label: "ATS optimization" },
  { value: "<3 min", label: "per application" },
];

const FEATURES_SECTION_TITLE = "Not just a resume builder — a career intelligence system";

/* ── Interactive Demo Component ── */

const DEMO_AGENTS = [
  { name: "Recon", role: "Intel Gatherer", color: "text-cyan-500", bg: "bg-cyan-500/10", logs: ["Researching company culture...", "Analyzing tech stack: React, Node.js, AWS", "Found 3 recent news articles", "Intel report ready"] },
  { name: "Atlas", role: "Resume Analyst", color: "text-blue-500", bg: "bg-blue-500/10", logs: ["Parsing resume sections...", "Detected 12 skills, 4 roles", "Building candidate benchmark", "Profile analysis complete"] },
  { name: "Cipher", role: "Gap Detector", color: "text-amber-500", bg: "bg-amber-500/10", logs: ["Comparing against JD requirements...", "Found 3 skill gaps, 2 keyword misses", "Generating improvement priorities", "Gap analysis ready"] },
  { name: "Quill", role: "Document Architect", color: "text-violet-500", bg: "bg-violet-500/10", logs: ["Generating ATS-optimized CV...", "Tailoring cover letter narrative...", "Building personal statement", "Documents crafted"] },
  { name: "Sentinel", role: "Quality Inspector", color: "text-emerald-500", bg: "bg-emerald-500/10", logs: ["Validating keyword coverage: 94%", "ATS format check: PASS", "Readability score: 92/100", "All quality checks passed"] },
];

function DemoAgentTimeline() {
  const [activeIdx, setActiveIdx] = useState(0);
  const [logIdx, setLogIdx] = useState(0);
  const [completed, setCompleted] = useState<Set<number>>(new Set());

  useEffect(() => {
    const interval = setInterval(() => {
      setLogIdx((prev) => {
        const agent = DEMO_AGENTS[activeIdx];
        if (!agent) return prev;
        if (prev < agent.logs.length - 1) return prev + 1;
        // Agent complete, move to next
        setCompleted((c) => { const n = new Set(c); n.add(activeIdx); return n; });
        setActiveIdx((a) => {
          if (a < DEMO_AGENTS.length - 1) return a + 1;
          // Loop back
          setTimeout(() => { setCompleted(new Set()); setActiveIdx(0); setLogIdx(0); }, 2000);
          return a;
        });
        return 0;
      });
    }, 800);
    return () => clearInterval(interval);
  }, [activeIdx]);

  return (
    <div className="space-y-1">
      {DEMO_AGENTS.map((agent, i) => {
        const isDone = completed.has(i);
        const isActive = i === activeIdx && !isDone;
        return (
          <motion.div
            key={agent.name}
            initial={{ opacity: 0, x: -10 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.05 }}
            className="flex gap-3"
          >
            {/* Timeline dot */}
            <div className="flex flex-col items-center shrink-0 w-5">
              <div className={`h-5 w-5 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
                isDone ? "border-emerald-500 bg-emerald-500/10" : isActive ? "border-primary bg-primary/10" : "border-border bg-muted/50"
              }`}>
                {isDone ? (
                  <motion.svg initial={{ scale: 0 }} animate={{ scale: 1 }} className="h-3 w-3 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </motion.svg>
                ) : isActive ? (
                  <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                ) : (
                  <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
                )}
              </div>
              {i < DEMO_AGENTS.length - 1 && <div className={`w-0.5 flex-1 min-h-[4px] ${isDone ? "bg-emerald-500/30" : "bg-border"}`} />}
            </div>

            {/* Card */}
            <div className={`flex-1 rounded-lg px-3 py-2 mb-1 transition-all duration-300 ${
              isActive ? "bg-primary/[0.03] border border-primary/20" : isDone ? "opacity-70" : "opacity-40"
            }`}>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${isActive ? agent.color : isDone ? "text-emerald-500" : "text-muted-foreground/50"}`}>
                  {agent.name}
                </span>
                <span className="text-[10px] text-muted-foreground">{agent.role}</span>
              </div>
              {isActive && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-1.5">
                  <div className="rounded bg-zinc-950/80 p-2">
                    {DEMO_AGENTS[activeIdx].logs.slice(0, logIdx + 1).map((log, j) => (
                      <motion.p key={j} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-[10px] font-mono text-zinc-400">
                        <span className="text-zinc-600 mr-1.5">{String(j + 1).padStart(2, "0")}</span>{log}
                      </motion.p>
                    ))}
                  </div>
                </motion.div>
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ── */}
      <header className="fixed top-0 z-50 w-full border-b bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-glow-sm">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight">
              HireStack <span className="text-primary">AI</span>
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/#how-it-works" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              How It Works
            </Link>
            <Link href="/login" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Sign In
            </Link>
            <Link href="/login?mode=register&redirect=/new" className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-glow-sm hover:shadow-glow-md transition-all hover:brightness-110">
              Get Started <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden pt-32 pb-20">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -left-32 top-0 h-[500px] w-[500px] rounded-full bg-primary/5 blur-3xl" />
          <div className="absolute -right-32 top-32 h-[400px] w-[400px] rounded-full bg-violet-500/5 blur-3xl" />
          <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-500/5 blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-6xl px-4 text-center">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border bg-card/80 px-4 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur-sm animate-in fade-in slide-in-from-bottom-2 duration-700">
            <Zap className="h-3.5 w-3.5 text-primary" />
            Most candidates submit claims. The best submit proof.
          </div>

          <h1 className="mx-auto max-w-4xl text-3xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl animate-in fade-in slide-in-from-bottom-4 duration-700 delay-100 fill-mode-both">
            Turn any job description into a{" "}
            <span className="gradient-text">proof-backed application</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed animate-in fade-in slide-in-from-bottom-4 duration-700 delay-200 fill-mode-both">
            Paste a job description. Add your resume. Get a tailored application
            with ATS-optimized documents, gap analysis, evidence mapping, and
            interview preparation — in minutes, not hours.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row animate-in fade-in slide-in-from-bottom-4 duration-700 delay-300 fill-mode-both">
            <Link href="/login?mode=register&redirect=/new" className="group inline-flex items-center gap-2 rounded-2xl bg-primary px-8 py-4 text-base font-semibold text-primary-foreground shadow-glow-md hover:shadow-glow-lg transition-all hover:brightness-110">
              Start Your Application
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <a href="#how-it-works" className="inline-flex items-center gap-2 rounded-2xl border px-8 py-4 text-base font-medium text-foreground hover:bg-muted/50 transition-colors">
              See How It Works
            </a>
          </div>

          <p className="mt-4 text-xs text-muted-foreground/60 animate-in fade-in duration-1000 delay-500 fill-mode-both">
            Create an account to save, edit, and export your documents.
          </p>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="mx-auto mt-16 grid max-w-2xl grid-cols-2 gap-6 sm:grid-cols-4"
          >
            {STATS.map((s, i) => (
              <div key={i} className="text-center">
                <div className="text-2xl font-bold tracking-tight sm:text-3xl">{s.value}</div>
                <div className="mt-1 text-xs text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Live Demo Preview ── */}
      <section className="border-t py-20 bg-gradient-to-b from-background to-card/30">
        <div className="mx-auto max-w-5xl px-4">
          <div className="text-center mb-12">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              <Sparkles className="h-3.5 w-3.5" /> See it in action
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Watch AI agents build your application
            </h2>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="rounded-2xl border bg-card shadow-soft-lg overflow-hidden"
          >
            {/* Simulated browser chrome */}
            <div className="flex items-center gap-2 px-4 py-3 border-b bg-muted/30">
              <div className="flex gap-1.5">
                <div className="h-3 w-3 rounded-full bg-rose-400" />
                <div className="h-3 w-3 rounded-full bg-amber-400" />
                <div className="h-3 w-3 rounded-full bg-emerald-400" />
              </div>
              <div className="flex-1 flex justify-center">
                <div className="rounded-lg bg-muted/60 px-4 py-1 text-[10px] text-muted-foreground font-mono">
                  hirestack.tech/new
                </div>
              </div>
            </div>

            {/* Simulated pipeline */}
            <div className="p-6">
              <DemoAgentTimeline />
            </div>
          </motion.div>
        </div>
      </section>

      {/* ── What You Get (Real Product Preview) ── */}
      <section className="border-t py-20">
        <div className="mx-auto max-w-5xl px-4">
          <div className="text-center mb-12">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-emerald-500/5 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" /> What you get
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              A complete application workspace, not just a resume
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              Every application generates a tailored workspace with analysis, documents, and improvement plan.
            </p>
          </div>

          {/* Preview cards showing real output types */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              {
                title: "Fit Analysis",
                desc: "Match score with breakdown of which requirements you meet, partially meet, or miss entirely.",
                sample: "87% match — 12 of 14 requirements met",
                color: "text-emerald-600 bg-emerald-500/10",
              },
              {
                title: "Missing Keywords",
                desc: "Exact phrases the ATS is looking for that aren't in your resume yet.",
                sample: "5 missing: CI/CD, Terraform, GraphQL, k8s, observability",
                color: "text-blue-600 bg-blue-500/10",
              },
              {
                title: "Evidence Suggestions",
                desc: "Specific proof items you should attach to turn claims into verifiable facts.",
                sample: "3 suggestions: link GitHub repo, add AWS cert, quantify team size",
                color: "text-amber-600 bg-amber-500/10",
              },
              {
                title: "Tailored Documents",
                desc: "ATS-optimized CV, cover letter, and role-specific documents written to match this exact role.",
                sample: "4 documents generated: CV, Cover Letter, Personal Statement, Portfolio Brief",
                color: "text-violet-600 bg-violet-500/10",
              },
              {
                title: "Gap Report",
                desc: "What you're missing vs the ideal candidate, with actionable steps to close each gap.",
                sample: "2 critical gaps: cloud architecture experience, team leadership examples",
                color: "text-rose-600 bg-rose-500/10",
              },
              {
                title: "Interview Readiness",
                desc: "Likely questions based on the JD, with suggested answers using your actual experience.",
                sample: "8 predicted questions with STAR-format answer outlines",
                color: "text-primary bg-primary/10",
              },
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border bg-card p-5"
              >
                <h3 className="text-sm font-semibold">{item.title}</h3>
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
                <div className={`mt-3 rounded-lg px-3 py-2 text-[11px] font-medium ${item.color}`}>
                  {item.sample}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section id="how-it-works" className="border-t bg-card/30 py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="text-center mb-16">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              <Globe className="h-3.5 w-3.5" /> How it works
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              From job description to tailored application in 3 minutes
            </h2>
          </div>

          <div className="mx-auto grid max-w-4xl gap-0 md:grid-cols-4">
            {STEPS.map((step, i) => (
              <motion.div
                key={step.n}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="relative flex flex-col items-center text-center px-4 py-6"
              >
                {i < 3 && (
                  <div className="absolute right-0 top-10 hidden h-px w-full md:block bg-gradient-to-r from-border to-transparent" />
                )}
                <div className="relative z-10 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-violet-600 text-white shadow-glow-sm mb-4">
                  <step.icon className="h-6 w-6" />
                </div>
                <h3 className="text-sm font-bold">{step.title}</h3>
                <p className="mt-2 text-xs text-muted-foreground leading-relaxed">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="border-t py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="text-center mb-16">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              <Target className="h-3.5 w-3.5" /> Features
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Not just a resume builder — a career intelligence system
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              Every feature designed to give you an unfair advantage.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {FEATURES.map((f, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="group rounded-2xl border bg-card p-6 shadow-soft-sm hover:shadow-soft-md transition-all duration-300 hover:-translate-y-0.5"
              >
                <div className={`mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${f.gradient}`}>
                  <div className={f.iconColor}>{f.icon}</div>
                </div>
                <h3 className="text-base font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Trust & Methodology ── */}
      <section className="border-t bg-card/30 py-16">
        <div className="mx-auto max-w-4xl px-4">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold tracking-tight">Why this works</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Built on proven hiring research and ATS analysis methodology.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-3">
            {[
              {
                title: "Requirement extraction",
                desc: "AI parses every explicit and implicit requirement from the job description, including keywords, responsibilities, and qualifications the ATS checks for.",
              },
              {
                title: "Evidence mapping",
                desc: "Instead of generic claims, we map your specific experience, certifications, and projects to each requirement — turning assertions into verifiable proof.",
              },
              {
                title: "ATS optimization",
                desc: "Documents are structured and formatted to pass automated screening systems, with keyword density, section headers, and formatting that ATS software expects.",
              },
            ].map((item, i) => (
              <div key={i} className="rounded-xl border bg-card p-5">
                <h3 className="text-sm font-semibold">{item.title}</h3>
                <p className="mt-2 text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Bottom CTA ── */}
      <section className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-24">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-12 text-center shadow-glow-lg md:p-16"
          >
            <div className="pointer-events-none absolute inset-0 opacity-10">
              <div className="absolute -right-20 -top-20 h-[300px] w-[300px] rounded-full border-[40px] border-white/20" />
              <div className="absolute -bottom-10 -left-10 h-[200px] w-[200px] rounded-full border-[30px] border-white/20" />
            </div>

            <div className="relative z-10">
              <h2 className="text-3xl font-bold text-white sm:text-4xl">
                Ready to build a stronger application?
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-base text-white/80">
                Paste a job description, add your resume, and let AI build a
                tailored, proof-backed application package.
              </p>
              <Link href="/login?mode=register&redirect=/new" className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-base font-semibold text-primary shadow-soft-lg hover:shadow-soft-xl transition-all hover:scale-[1.02]">
                Start Your Application
                <ArrowRight className="h-4 w-4" />
              </Link>
              <p className="mt-3 text-xs text-white/50">
                Create an account to save, edit, and export.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t bg-card/30 py-12">
        <div className="mx-auto max-w-6xl px-4">
          <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet-600">
                <Sparkles className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-sm font-bold">HireStack <span className="text-primary">AI</span></span>
            </div>
            <div className="flex items-center gap-6 text-xs text-muted-foreground">
              <Link href="/#how-it-works" className="hover:text-foreground transition-colors">How It Works</Link>
              <Link href="/login" className="hover:text-foreground transition-colors">Sign In</Link>
              <Link href="/login?mode=register&redirect=/new" className="hover:text-foreground transition-colors">Get Started</Link>
            </div>
            <p className="text-xs text-muted-foreground">
              &copy; {new Date().getFullYear()} HireStack AI
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
