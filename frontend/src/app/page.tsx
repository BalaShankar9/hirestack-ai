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
    title: "AI Agent Swarm",
    description: "6 specialized AI agents work in parallel — Atlas parses, Cipher finds gaps, Quill writes, Forge builds portfolios, Sentinel validates, Nova assembles.",
  },
  {
    icon: <Target className="h-5 w-5" />,
    gradient: "from-emerald-500/10 to-teal-500/10",
    iconColor: "text-emerald-600",
    title: "Company Intelligence",
    description: "Our Recon agent researches the company before writing a single word. Culture, tech stack, recent news — all woven into your application.",
  },
  {
    icon: <BarChart3 className="h-5 w-5" />,
    gradient: "from-blue-500/10 to-cyan-500/10",
    iconColor: "text-blue-600",
    title: "ATS Scanner",
    description: "See your resume through the recruiter's ATS. Keyword match scoring, format analysis, and real-time optimization suggestions.",
  },
  {
    icon: <Shield className="h-5 w-5" />,
    gradient: "from-amber-500/10 to-orange-500/10",
    iconColor: "text-amber-600",
    title: "Evidence Vault",
    description: "Attach certifications, projects, and metrics directly to your claims. Every statement backed by verifiable proof.",
  },
  {
    icon: <TrendingUp className="h-5 w-5" />,
    gradient: "from-rose-500/10 to-pink-500/10",
    iconColor: "text-rose-600",
    title: "Gap Analysis",
    description: "See exactly what you're missing vs the ideal candidate. Get a sprint-based learning plan to close every gap.",
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
  { value: "6", label: "AI agents" },
  { value: "94%", label: "ATS pass rate" },
  { value: "<3 min", label: "per application" },
];

const LOGOS_TEXT = ["TechCrunch", "Product Hunt", "Hacker News", "Forbes"];

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
            <Link href="/pricing" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </Link>
            <Link href="/login" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Sign In
            </Link>
            <Link href="/new" className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-glow-sm hover:shadow-glow-md transition-all hover:brightness-110">
              Try Free <ArrowRight className="h-3.5 w-3.5" />
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
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <div className="mb-8 inline-flex items-center gap-2 rounded-full border bg-card/80 px-4 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur-sm">
              <Zap className="h-3.5 w-3.5 text-primary" />
              AI-powered career intelligence platform
            </div>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="mx-auto max-w-4xl text-3xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl"
          >
            Stop applying.{" "}
            <span className="gradient-text">Start landing.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed"
          >
            6 AI agents collaborate to build your perfect application package —
            ATS-optimized CV, tailored cover letter, portfolio, and more. Powered by
            company intelligence and gap analysis.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row"
          >
            <Link href="/new" className="group inline-flex items-center gap-2 rounded-2xl bg-primary px-8 py-4 text-base font-semibold text-primary-foreground shadow-glow-md hover:shadow-glow-lg transition-all hover:brightness-110">
              Build Your Application — Free
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link href="/pricing" className="inline-flex items-center gap-2 rounded-2xl border px-8 py-4 text-base font-medium text-foreground hover:bg-muted/50 transition-colors">
              View Pricing
            </Link>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-4 text-xs text-muted-foreground/60"
          >
            No signup required. No credit card. Start building in 10 seconds.
          </motion.p>

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

      {/* ── How It Works ── */}
      <section className="border-t bg-card/30 py-24">
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

      {/* ── Social Proof ── */}
      <section className="border-t bg-card/30 py-16">
        <div className="mx-auto max-w-4xl px-4">
          <div className="flex items-center justify-center gap-8 opacity-30">
            {LOGOS_TEXT.map((name, i) => (
              <span key={i} className="text-sm font-bold tracking-wider uppercase">{name}</span>
            ))}
          </div>
          <div className="mt-8 flex items-center justify-center gap-1">
            {[...Array(5)].map((_, i) => (
              <Star key={i} className="h-4 w-4 fill-amber-400 text-amber-400" />
            ))}
            <span className="ml-2 text-sm text-muted-foreground">
              Rated 4.9/5 by 2,000+ professionals
            </span>
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
                Your next interview starts here
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-base text-white/80">
                Join thousands of professionals who stopped guessing and started winning.
              </p>
              <Link href="/new" className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-base font-semibold text-primary shadow-soft-lg hover:shadow-soft-xl transition-all hover:scale-[1.02]">
                Try It Now — No Signup Required
                <ArrowRight className="h-4 w-4" />
              </Link>
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
              <Link href="/pricing" className="hover:text-foreground transition-colors">Pricing</Link>
              <Link href="/login" className="hover:text-foreground transition-colors">Sign In</Link>
              <Link href="/new" className="hover:text-foreground transition-colors">Try Free</Link>
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
