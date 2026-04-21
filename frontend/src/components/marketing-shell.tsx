import Link from "next/link";
import { Sparkles, ArrowRight } from "lucide-react";

export function MarketingShell({
  title,
  kicker,
  description,
  children,
}: {
  title: string;
  kicker?: React.ReactNode;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background pb-24">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 sticky top-0 z-40">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-glow-sm">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <span className="text-base font-bold">
              HireStack <span className="text-primary">AI</span>
            </span>
          </Link>
          <nav className="hidden md:flex items-center gap-5 text-sm">
            <Link href="/#how-it-works" className="text-muted-foreground hover:text-foreground transition-colors">
              How it works
            </Link>
            <Link href="/#features" className="text-muted-foreground hover:text-foreground transition-colors">
              Features
            </Link>
            <Link href="/#pricing" className="text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </Link>
            <Link
              href="/login?mode=register&redirect=/new"
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground btn-glow hover:shadow-glow-md transition-all hover:brightness-110"
            >
              Start free <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </nav>
          <Link
            href="/login?mode=register&redirect=/new"
            className="md:hidden inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
          >
            Start free
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="border-b bg-gradient-to-b from-primary/[0.04] via-background to-background py-16">
        <div className="mx-auto max-w-3xl px-4 text-center">
          {kicker && (
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
              {kicker}
            </div>
          )}
          <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">{title}</h1>
          {description && (
            <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground leading-relaxed">
              {description}
            </p>
          )}
        </div>
      </section>

      {/* Content */}
      <main className="mx-auto max-w-5xl px-4 py-16">{children}</main>

      {/* Bottom CTA */}
      <section className="border-t bg-card/30 py-16">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Ready to land your next role?
          </h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Free to start. No credit card. 6 AI agents. 3 minutes.
          </p>
          <Link
            href="/login?mode=register&redirect=/new"
            className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-primary px-7 py-3.5 text-sm font-bold text-primary-foreground btn-glow hover:shadow-glow-md transition-all hover:brightness-110"
          >
            Start your application <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 text-xs text-muted-foreground md:flex-row">
          <p>&copy; {new Date().getFullYear()} HireStack AI</p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link href="/about" className="hover:text-foreground transition-colors">About</Link>
            <Link href="/security" className="hover:text-foreground transition-colors">Security</Link>
            <Link href="/contact" className="hover:text-foreground transition-colors">Contact</Link>
            <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
            <Link href="/terms" className="hover:text-foreground transition-colors">Terms</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
