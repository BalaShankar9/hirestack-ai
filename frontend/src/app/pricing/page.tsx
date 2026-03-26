"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Check, Sparkles, Zap, Crown, Building2, Star } from "lucide-react";
import { PLANS } from "@/lib/plans";
import { cn } from "@/lib/utils";

const PLAN_ICONS = [Zap, Zap, Crown, Building2];
const PLAN_GRADIENTS = [
  "from-zinc-500 to-gray-600",
  "from-blue-500 to-cyan-500",
  "from-violet-500 to-purple-600",
  "from-amber-500 to-orange-500",
];

const FAQ = [
  { q: "Can I try HireStack for free?", a: "Yes! Create applications and generate all documents without signing up. You only need an account to download." },
  { q: "How does the free plan work?", a: "After signing up, you get 5 free document exports per month — PDFs, DOCX, and images of your CV, cover letters, and more." },
  { q: "What's included in annual billing?", a: "Pay annually and save 20%. All features are the same — you just get 2 months free." },
  { q: "Can I cancel anytime?", a: "Yes. Cancel from your billing settings — no contracts, no questions asked. You keep access until the end of your billing period." },
  { q: "What payment methods do you accept?", a: "All major credit/debit cards via Stripe. Enterprise plans can pay by invoice." },
  { q: "Is my data secure?", a: "Yes. We use bank-level encryption (AES-256), SOC 2 compliant infrastructure, and never share your data with third parties." },
];

const TESTIMONIALS = [
  { name: "Sarah K.", role: "Product Manager", text: "Landed my dream role at a FAANG company. The AI-generated CV was perfect.", avatar: "SK" },
  { name: "James L.", role: "Software Engineer", text: "The company intel feature gave me insights no other tool could. Worth every penny.", avatar: "JL" },
  { name: "Priya M.", role: "Data Scientist", text: "Generated 15 tailored applications in one weekend. Got 8 interviews.", avatar: "PM" },
];

export default function PricingPage() {
  const [annual, setAnnual] = useState(false);

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
            <Link href="/new" className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-glow-sm hover:shadow-glow-md transition-all">
              Try Free <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-32 pb-8 text-center">
        <div className="mx-auto max-w-3xl px-4">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border bg-card/80 px-4 py-1.5 text-xs font-medium text-muted-foreground">
              <Zap className="h-3.5 w-3.5 text-primary" /> Simple, transparent pricing
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
              Invest in your career, not guesswork
            </h1>
            <p className="mt-4 text-lg text-muted-foreground max-w-xl mx-auto">
              Start free. Upgrade when you&apos;re ready. Cancel anytime.
            </p>
          </motion.div>

          {/* Billing toggle */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="mt-8 flex items-center justify-center gap-3"
          >
            <span className={cn("text-sm font-medium transition-colors", !annual ? "text-foreground" : "text-muted-foreground")}>
              Monthly
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              className={cn(
                "relative h-7 w-14 rounded-full transition-colors duration-300",
                annual ? "bg-primary" : "bg-muted"
              )}
            >
              <motion.div
                className="absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow-sm"
                animate={{ x: annual ? 28 : 0 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
              />
            </button>
            <span className={cn("text-sm font-medium transition-colors", annual ? "text-foreground" : "text-muted-foreground")}>
              Annual
            </span>
            {annual && (
              <motion.span
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold text-emerald-600"
              >
                Save 20%
              </motion.span>
            )}
          </motion.div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-24">
        <div className="mx-auto max-w-5xl px-4">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {PLANS.map((plan, i) => {
              const Icon = PLAN_ICONS[i];
              const monthlyPrice = annual ? Math.round(plan.price * 0.8) : plan.price;
              return (
                <motion.div
                  key={plan.key}
                  initial={{ opacity: 0, y: 30 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + i * 0.08, duration: 0.4 }}
                  className={cn(
                    "relative rounded-2xl border p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-soft-lg",
                    plan.popular
                      ? "border-primary shadow-glow-sm bg-primary/[0.02] ring-1 ring-primary/20"
                      : "bg-card hover:border-primary/30"
                  )}
                >
                  {plan.popular && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.4 }}
                      className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-[10px] font-semibold text-primary-foreground shadow-glow-sm"
                    >
                      Most Popular
                    </motion.div>
                  )}

                  <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${PLAN_GRADIENTS[i]} shadow-sm mb-4`}>
                    <Icon className="h-5 w-5 text-white" />
                  </div>

                  <h3 className="text-lg font-bold">{plan.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    {monthlyPrice === 0 ? (
                      <span className="text-3xl font-bold">Free</span>
                    ) : (
                      <>
                        <motion.span
                          key={monthlyPrice}
                          initial={{ opacity: 0, y: -10 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="text-3xl font-bold"
                        >
                          ${monthlyPrice}
                        </motion.span>
                        <span className="text-sm text-muted-foreground">/mo</span>
                      </>
                    )}
                  </div>
                  {annual && plan.price > 0 && (
                    <motion.p
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="text-[10px] text-emerald-600 font-medium mt-0.5"
                    >
                      ${monthlyPrice * 12}/year (save ${plan.price * 12 - monthlyPrice * 12})
                    </motion.p>
                  )}

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
                    className={cn(
                      "mt-6 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all",
                      plan.popular
                        ? "bg-primary text-primary-foreground shadow-glow-sm hover:shadow-glow-md hover:brightness-110"
                        : "border bg-background hover:bg-muted/50"
                    )}
                  >
                    {plan.price === 0 ? "Get Started Free" : `Start with ${plan.name}`}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="border-t bg-card/30 py-20">
        <div className="mx-auto max-w-4xl px-4">
          <h2 className="text-2xl font-bold text-center mb-12">Loved by professionals worldwide</h2>
          <div className="grid gap-6 md:grid-cols-3">
            {TESTIMONIALS.map((t, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="rounded-2xl border bg-card p-5"
              >
                <div className="flex gap-0.5 mb-3">
                  {[...Array(5)].map((_, j) => (
                    <Star key={j} className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                  ))}
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">&ldquo;{t.text}&rdquo;</p>
                <div className="mt-4 flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-violet-500/20 text-[10px] font-bold text-primary">
                    {t.avatar}
                  </div>
                  <div>
                    <p className="text-xs font-semibold">{t.name}</p>
                    <p className="text-[10px] text-muted-foreground">{t.role}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t py-20">
        <div className="mx-auto max-w-3xl px-4">
          <h2 className="text-2xl font-bold text-center mb-12">Frequently asked questions</h2>
          <div className="space-y-4">
            {FAQ.map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border bg-card p-5"
              >
                <h3 className="font-semibold text-sm">{item.q}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{item.a}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="border-t py-20">
        <div className="mx-auto max-w-6xl px-4">
          <div className="rounded-3xl bg-gradient-to-br from-primary via-violet-600 to-indigo-700 p-12 text-center shadow-glow-lg">
            <h2 className="text-3xl font-bold text-white">Your next role starts here</h2>
            <p className="mt-4 text-white/80 max-w-lg mx-auto">
              Join thousands of professionals using AI to land their dream roles.
            </p>
            <Link href="/new" className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-base font-semibold text-primary shadow-soft-lg hover:shadow-soft-xl transition-all hover:scale-[1.02]">
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
          <p className="text-xs text-muted-foreground">&copy; {new Date().getFullYear()} HireStack AI</p>
        </div>
      </footer>
    </div>
  );
}
