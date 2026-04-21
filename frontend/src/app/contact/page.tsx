import type { Metadata } from "next";
import Link from "next/link";
import { MarketingShell } from "@/components/marketing-shell";
import { Mail, MessageSquare, Twitter, BookOpen } from "lucide-react";

export const metadata: Metadata = {
  title: "Contact — Talk to the team",
  description: "Questions, partnerships, press, or support? We reply within one business day.",
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  const channels = [
    {
      icon: Mail,
      title: "Support",
      body: "Account, billing, or product issues — we're on it.",
      cta: "support@hirestack.tech",
      href: "mailto:support@hirestack.tech",
    },
    {
      icon: MessageSquare,
      title: "Enterprise & partnerships",
      body: "Career+ plans, team licences, or integrations.",
      cta: "hello@hirestack.tech",
      href: "mailto:hello@hirestack.tech",
    },
    {
      icon: BookOpen,
      title: "Press",
      body: "Media enquiries and interview requests.",
      cta: "press@hirestack.tech",
      href: "mailto:press@hirestack.tech",
    },
    {
      icon: Twitter,
      title: "On social",
      body: "Product updates and career tips, daily.",
      cta: "@hirestack",
      href: "https://twitter.com/hirestack",
    },
  ];
  return (
    <MarketingShell
      kicker={<><Mail className="h-3.5 w-3.5" /> Contact</>}
      title="Let's talk."
      description="We're a small team that reads every message. Pick the channel that fits — we'll be back within one business day."
    >
      <div className="grid gap-5 md:grid-cols-2">
        {channels.map((c, i) => (
          <Link
            key={i}
            href={c.href}
            className="group rounded-2xl border bg-card p-6 hover:shadow-soft-md hover:-translate-y-0.5 transition-all"
          >
            <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary group-hover:bg-primary group-hover:text-white transition-colors">
              <c.icon className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold">{c.title}</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{c.body}</p>
            <p className="mt-4 text-sm font-semibold text-primary group-hover:underline">
              {c.cta} →
            </p>
          </Link>
        ))}
      </div>
    </MarketingShell>
  );
}
