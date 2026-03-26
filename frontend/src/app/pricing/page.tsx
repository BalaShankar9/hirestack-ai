import Link from "next/link";
import { ArrowRight, Check, Sparkles, Zap, Crown, Building2 } from "lucide-react";
import { PLANS } from "@/lib/plans";

const PLAN_ICONS = [Zap, Zap, Crown, Building2];
const PLAN_COLORS = [
  "from-gray-500/10 to-zinc-500/10",
  "from-blue-500/10 to-cyan-500/10",
  "from-violet-500/10 to-purple-500/10",
  "from-amber-500/10 to-orange-500/10",
];

const FAQ = [
  {
    q: "Can I try HireStack for free?",
    a: "Yes! You can create applications and generate all documents without signing up. You only need an account to download your documents.",
  },
  {
    q: "How does the free plan work?",
    a: "After signing up, you get 5 free document exports per month. This includes PDFs, DOCX files, and images of your CV, cover letters, and other documents.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes, all paid plans are month-to-month. Cancel anytime from your billing settings — no contracts, no questions asked.",
  },
  {
    q: "What payment methods do you accept?",
    a: "We accept all major credit and debit cards through Stripe. Enterprise plans can also pay by invoice.",
  },
  {
    q: "Do you offer refunds?",
    a: "Yes, we offer a 14-day money-back guarantee on all paid plans. If you're not satisfied, contact us for a full refund.",
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
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
            <Link href="/login" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Sign In
            </Link>
            <Link href="/new" className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-glow-sm hover:shadow-glow-md transition-all hover:brightness-110">
              Try Free <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-32 pb-16 text-center">
        <div className="mx-auto max-w-3xl px-4">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border bg-card/80 px-4 py-1.5 text-xs font-medium text-muted-foreground">
            <Zap className="h-3.5 w-3.5 text-primary" /> Simple, transparent pricing
          </div>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Start free, scale as you grow
          </h1>
          <p className="mt-4 text-lg text-muted-foreground max-w-xl mx-auto">
            Build your first application for free — no credit card required. Upgrade when you need more power.
          </p>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-24">
        <div className="mx-auto max-w-5xl px-4">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {PLANS.map((plan, i) => {
              const Icon = PLAN_ICONS[i];
              return (
                <div
                  key={plan.key}
                  className={`relative rounded-2xl border p-6 transition-all hover:-translate-y-0.5 hover:shadow-soft-md ${
                    plan.popular ? "border-primary shadow-glow-sm bg-primary/[0.02] ring-1 ring-primary/20" : "bg-card"
                  }`}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-[10px] font-semibold text-primary-foreground">
                      Most Popular
                    </div>
                  )}

                  <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${PLAN_COLORS[i]} mb-4`}>
                    <Icon className="h-5 w-5 text-foreground/70" />
                  </div>

                  <h3 className="text-lg font-bold">{plan.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    {plan.price === 0 ? (
                      <span className="text-3xl font-bold">Free</span>
                    ) : (
                      <>
                        <span className="text-3xl font-bold">${plan.price}</span>
                        <span className="text-sm text-muted-foreground">/mo</span>
                      </>
                    )}
                  </div>

                  <ul className="mt-6 space-y-2.5">
                    {plan.features.map((f, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm text-muted-foreground">
                        <Check className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  <Link
                    href={plan.price === 0 ? "/new" : "/login?mode=register&redirect=/settings/billing"}
                    className={`mt-6 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
                      plan.popular
                        ? "bg-primary text-primary-foreground shadow-glow-sm hover:shadow-glow-md hover:brightness-110"
                        : "border bg-background hover:bg-muted/50"
                    }`}
                  >
                    {plan.price === 0 ? "Get Started Free" : `Upgrade to ${plan.name}`}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t bg-card/30 py-24">
        <div className="mx-auto max-w-3xl px-4">
          <h2 className="text-2xl font-bold text-center mb-12">Frequently asked questions</h2>
          <div className="space-y-6">
            {FAQ.map((item, i) => (
              <div key={i} className="rounded-2xl border bg-card p-5">
                <h3 className="font-semibold text-sm">{item.q}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="rounded-3xl bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-12 text-center shadow-glow-lg">
            <h2 className="text-3xl font-bold text-white">Ready to build better applications?</h2>
            <p className="mt-4 text-white/80 max-w-lg mx-auto">
              Join thousands of professionals using AI to land their dream roles.
            </p>
            <Link
              href="/new"
              className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-base font-semibold text-primary shadow-soft-lg hover:shadow-soft-xl transition-all hover:scale-[1.02]"
            >
              Try It Now — No Signup Required
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t bg-card/30 py-12">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 md:flex-row">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet-600">
              <Sparkles className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-sm font-bold">HireStack <span className="text-primary">AI</span></span>
          </div>
          <p className="text-xs text-muted-foreground">
            &copy; {new Date().getFullYear()} HireStack AI
          </p>
        </div>
      </footer>
    </div>
  );
}
