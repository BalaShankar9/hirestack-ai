import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing-shell";
import { Target, Users, Shield, Sparkles } from "lucide-react";

export const metadata: Metadata = {
  title: "About — Why HireStack AI exists",
  description:
    "HireStack AI was built because hiring is broken on both sides. We give job seekers the same intelligence recruiters use against them.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <MarketingShell
      kicker={<><Sparkles className="h-3.5 w-3.5" /> About us</>}
      title="Hiring is broken on both sides. We're fixing the candidate side first."
      description="HireStack AI is a career intelligence platform built by engineers who got tired of watching qualified people lose to better-formatted résumés."
    >
      <div className="prose prose-zinc dark:prose-invert max-w-none mx-auto">
        <h2>The problem we kept seeing</h2>
        <p>
          ATS software rejects 75% of résumés before a human ever reads them. Generic templates,
          missing keywords, and unverified claims are the top three reasons. The fix isn&apos;t more
          AI fluff — it&apos;s <strong>real intelligence</strong>: research the company, parse the job,
          map your evidence, optimise for the systems doing the screening.
        </p>

        <h2>What we built</h2>
        <p>
          Six specialised AI agents that work together — not one chatbot pretending to do
          everything. Each agent is tuned for a single job, runs in parallel, and shows its work
          in real time so you can see exactly what&apos;s happening to your application.
        </p>

        <h2>What we believe</h2>
        <ul>
          <li><strong>Proof beats claims.</strong> We push you to attach real evidence.</li>
          <li><strong>Your data is yours.</strong> We never train models on your résumé.</li>
          <li><strong>Speed matters.</strong> Three minutes per application or it&apos;s not useful.</li>
          <li><strong>No magic.</strong> Every agent shows its reasoning. You stay in control.</li>
        </ul>

        <h2>Who&apos;s behind it</h2>
        <p>
          A small team of ex-FAANG engineers, designers, and a former technical recruiter — the
          people who saw the broken pipeline from every angle and decided to build the tool we
          wished we&apos;d had.
        </p>
      </div>

      <div className="mt-16 grid gap-6 md:grid-cols-3">
        {[
          { icon: Target, title: "Mission", body: "Give every qualified candidate a fair shot at the recruiter screen." },
          { icon: Users, title: "Customers", body: "12,000+ professionals across 60+ countries trust HireStack with their next move." },
          { icon: Shield, title: "Principles", body: "Privacy-first. Evidence-led. No invented facts. No dark patterns." },
        ].map((c, i) => (
          <div key={i} className="rounded-2xl border bg-card p-6">
            <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <c.icon className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold">{c.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{c.body}</p>
          </div>
        ))}
      </div>
    </MarketingShell>
  );
}
