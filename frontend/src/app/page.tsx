import Link from "next/link";
import { ArrowRight, Target, Sparkles, TrendingUp, Zap, Shield, BarChart3, CheckCircle2 } from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ──────────────────────────────────── */}
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
            <Link
              href="/login"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/login?mode=register"
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-glow-sm hover:shadow-glow-md transition-all hover:brightness-110"
            >
              Get Started
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-32 pb-20">
        {/* Background orbs */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -left-32 top-0 h-[500px] w-[500px] rounded-full bg-primary/5 blur-3xl" />
          <div className="absolute -right-32 top-32 h-[400px] w-[400px] rounded-full bg-violet-500/5 blur-3xl" />
          <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-500/5 blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-6xl px-4 text-center">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border bg-card/80 px-4 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur-sm animate-fade-up">
            <Zap className="h-3.5 w-3.5 text-primary" />
            AI-powered career intelligence platform
          </div>

          <h1 className="mx-auto max-w-4xl text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl animate-fade-up">
            Build{" "}
            <span className="gradient-text">interview-winning</span>{" "}
            applications
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed animate-fade-up" style={{ animationDelay: "100ms" }}>
            Benchmark against elite candidates, identify your gaps, build proof,
            and ship tailored application packages — all powered by AI coaching.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row animate-fade-up" style={{ animationDelay: "200ms" }}>
            <Link
              href="/login?mode=register"
              className="inline-flex items-center gap-2 rounded-2xl bg-primary px-8 py-4 text-base font-semibold text-primary-foreground shadow-glow-md hover:shadow-glow-lg transition-all hover:brightness-110"
            >
              Start Free Analysis
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="#features"
              className="inline-flex items-center gap-2 rounded-2xl border px-8 py-4 text-base font-medium text-foreground hover:bg-muted/50 transition-colors"
            >
              See How It Works
            </Link>
          </div>

          {/* Stats strip */}
          <div className="mx-auto mt-20 grid max-w-2xl grid-cols-3 gap-8 animate-fade-up" style={{ animationDelay: "300ms" }}>
            <StatItem value="5 min" label="to first analysis" />
            <StatItem value="94%" label="keyword coverage" />
            <StatItem value="6" label="AI-generated modules" />
          </div>
        </div>
      </section>

      {/* ── Features ────────────────────────────────── */}
      <section id="features" className="border-t bg-card/30 py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="text-center">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              <Target className="h-3.5 w-3.5" />
              Features
            </div>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Everything you need to land the role
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              A complete system from diagnosis to delivery, not just another resume generator.
            </p>
          </div>

          <div className="mt-16 grid gap-6 md:grid-cols-3 animate-stagger">
            <FeatureCard
              icon={<Target className="h-5 w-5" />}
              color="from-primary/10 to-violet-500/10"
              iconColor="text-primary"
              title="Benchmark Generation"
              description="See what a winning candidate looks like. We generate a full benchmark package — rubric, keywords, and ideal profile — for any role."
            />
            <FeatureCard
              icon={<BarChart3 className="h-5 w-5" />}
              color="from-emerald-500/10 to-teal-500/10"
              iconColor="text-emerald-600"
              title="Gap Analysis"
              description="Your precise compatibility score with missing keywords, strengths, and an action queue. Every gap becomes a task."
            />
            <FeatureCard
              icon={<TrendingUp className="h-5 w-5" />}
              color="from-amber-500/10 to-orange-500/10"
              iconColor="text-amber-600"
              title="Learning Plan"
              description="Sprint-based skill building that produces proof artifacts. Each week ends with something for your Evidence Vault."
            />
            <FeatureCard
              icon={<Sparkles className="h-5 w-5" />}
              color="from-violet-500/10 to-purple-500/10"
              iconColor="text-violet-600"
              title="AI Coach Panel"
              description="Explainable, action-based guidance. Not generic tips — specific next steps based on your gaps and evidence."
            />
            <FeatureCard
              icon={<Shield className="h-5 w-5" />}
              color="from-blue-500/10 to-cyan-500/10"
              iconColor="text-blue-600"
              title="Evidence Vault"
              description="Collect certifications, projects, and links. Attach proof to your CV with one click. Claims backed by evidence."
            />
            <FeatureCard
              icon={<Zap className="h-5 w-5" />}
              color="from-rose-500/10 to-pink-500/10"
              iconColor="text-rose-600"
              title="Smart Documents"
              description="Tailored CV and cover letter with real-time keyword coverage tracking, diff view, and version history."
            />
          </div>
        </div>
      </section>

      {/* ── How It Works ────────────────────────────── */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              How it works
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
              Four steps from paste to polished application package.
            </p>
          </div>

          <div className="mx-auto mt-16 grid max-w-4xl gap-0 md:grid-cols-4">
            {[
              { n: "1", title: "Paste the JD", desc: "Add the job description and upload your resume." },
              { n: "2", title: "Lock facts", desc: "Review extracted keywords and confirm accuracy." },
              { n: "3", title: "Generate modules", desc: "Benchmark, gaps, learning plan, CV & cover letter." },
              { n: "4", title: "Iterate & ship", desc: "Use coach actions, attach evidence, export." },
            ].map((step, i) => (
              <div key={step.n} className="relative flex flex-col items-center text-center px-4 py-6">
                {i < 3 && (
                  <div className="absolute right-0 top-10 hidden h-px w-full md:block bg-gradient-to-r from-border to-transparent" />
                )}
                <div className="relative z-10 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground text-lg font-bold shadow-glow-sm">
                  {step.n}
                </div>
                <h3 className="mt-4 text-sm font-semibold">{step.title}</h3>
                <p className="mt-2 text-xs text-muted-foreground leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────── */}
      <section className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-24">
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-12 text-center shadow-glow-lg md:p-16">
            {/* Background pattern */}
            <div className="pointer-events-none absolute inset-0 opacity-10">
              <div className="absolute -right-20 -top-20 h-[300px] w-[300px] rounded-full border-[40px] border-white/20" />
              <div className="absolute -bottom-10 -left-10 h-[200px] w-[200px] rounded-full border-[30px] border-white/20" />
            </div>

            <div className="relative z-10">
              <h2 className="text-3xl font-bold text-white sm:text-4xl">
                Ready to transform your job search?
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-base text-white/80">
                Stop guessing. Start building proof-backed applications that beat 
                ATS filters and impress recruiters.
              </p>
              <Link
                href="/login?mode=register"
                className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-base font-semibold text-primary shadow-soft-lg hover:shadow-soft-xl transition-all hover:scale-[1.02]"
              >
                Get Started for Free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────── */}
      <footer className="border-t bg-card/30 py-12">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 md:flex-row">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet-600">
              <Sparkles className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-sm font-bold">
              HireStack <span className="text-primary">AI</span>
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} HireStack AI · Powered by Claude · Built for career success.
          </p>
        </div>
      </footer>
    </div>
  );
}

function StatItem({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <div className="text-2xl font-bold tracking-tight sm:text-3xl">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function FeatureCard({
  icon,
  color,
  iconColor,
  title,
  description,
}: {
  icon: React.ReactNode;
  color: string;
  iconColor: string;
  title: string;
  description: string;
}) {
  return (
    <div className="group rounded-2xl border bg-card p-6 shadow-soft-sm hover:shadow-soft-md transition-all duration-300 hover:-translate-y-0.5">
      <div className={`mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${color}`}>
        <div className={iconColor}>{icon}</div>
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}
