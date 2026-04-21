import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing-shell";
import { Shield, Lock, Server, Eye, KeyRound, FileCheck } from "lucide-react";

export const metadata: Metadata = {
  title: "Security — How we protect your data",
  description:
    "End-to-end encryption, SOC2-aligned controls, GDPR ready. Your résumé and job descriptions are never used to train AI models.",
  alternates: { canonical: "/security" },
};

export default function SecurityPage() {
  const items = [
    { icon: Lock, title: "Encryption everywhere", body: "TLS 1.3 in transit, AES-256 at rest. All connections to our APIs are HSTS-protected." },
    { icon: Server, title: "Hardened infrastructure", body: "Hosted on tier-1 cloud providers with isolated environments, automated patching, and least-privilege IAM." },
    { icon: KeyRound, title: "Auth done right", body: "Email magic links, OAuth, optional SSO on Career+. Passwords are hashed with argon2id." },
    { icon: Eye, title: "Zero training on your data", body: "We never share your résumé or generated content with model providers for training. Inference only." },
    { icon: FileCheck, title: "SOC2-aligned controls", body: "Documented incident response, change-management, vendor review, and quarterly access audits." },
    { icon: Shield, title: "GDPR & data rights", body: "Export your data anytime. Delete your account with one click — wipes within 30 days." },
  ];
  return (
    <MarketingShell
      kicker={<><Shield className="h-3.5 w-3.5" /> Security</>}
      title="Your career data deserves enterprise-grade protection"
      description="Security isn't a marketing checkbox — it's how we built HireStack from day one."
    >
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {items.map((it, i) => (
          <div key={i} className="rounded-2xl border bg-card p-6">
            <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <it.icon className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold">{it.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{it.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-16 rounded-2xl border bg-card/50 p-6 text-sm text-muted-foreground">
        <h3 className="text-base font-semibold text-foreground">Responsible disclosure</h3>
        <p className="mt-2 leading-relaxed">
          Found a vulnerability? Email <a href="mailto:security@hirestack.tech" className="text-primary hover:underline">security@hirestack.tech</a>{" "}
          with reproduction steps. We respond within 48 hours and credit researchers in our hall of fame.
        </p>
      </div>
    </MarketingShell>
  );
}
