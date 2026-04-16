import type { Metadata } from "next";
import Link from "next/link";
import { Sparkles } from "lucide-react";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "HireStack AI Privacy Policy — how we collect, use, and protect your data.",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Minimal header */}
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <span className="text-base font-bold">
              HireStack <span className="text-primary">AI</span>
            </span>
          </Link>
          <Link href="/" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            ← Back to home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="text-4xl font-bold tracking-tight">Privacy Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Last updated: April 2025
        </p>

        <div className="mt-10 space-y-10 text-sm leading-relaxed text-foreground/90">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Who we are</h2>
            <p>
              HireStack AI (&ldquo;we&rdquo;, &ldquo;our&rdquo;, or &ldquo;us&rdquo;) operates the HireStack AI platform
              at <a href="https://hirestack.tech" className="text-primary underline">hirestack.tech</a>. We help job
              seekers build tailored, evidence-backed applications using AI-powered analysis.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Information we collect</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>
                <strong>Account information:</strong> Email address and display name when you register.
              </li>
              <li>
                <strong>Resume &amp; career data:</strong> Resume files, job descriptions, and profile information
                you upload or enter — used solely to power your application generation.
              </li>
              <li>
                <strong>Usage data:</strong> Pages visited, features used, and interactions within the platform,
                collected to improve the service.
              </li>
              <li>
                <strong>Technical data:</strong> Browser type, IP address, and device information collected
                automatically via server logs.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. How we use your information</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>To provide, maintain, and improve the HireStack AI service.</li>
              <li>To generate AI-powered application documents tailored to your profile.</li>
              <li>To send transactional emails (account verification, password reset).</li>
              <li>To detect and prevent fraud, abuse, or security incidents.</li>
              <li>We do <strong>not</strong> sell your personal data to third parties.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">4. AI processing</h2>
            <p>
              Resume and job description content you submit is processed by AI models (Google Gemini via
              secure API calls) to produce application documents. This data is not used to train third-party
              AI models. Processing occurs transiently and results are stored in your account only.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">5. Data storage and security</h2>
            <p>
              Your data is stored in Supabase (PostgreSQL), hosted on infrastructure with encryption at rest
              and in transit. We implement rate limiting, authentication guards, and regular security reviews.
              No system is 100% secure; if you discover a vulnerability, please contact us immediately.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">6. Your rights</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong>Access:</strong> Request a copy of the personal data we hold about you.</li>
              <li><strong>Correction:</strong> Update inaccurate data via your account settings.</li>
              <li><strong>Deletion:</strong> Request deletion of your account and all associated data.</li>
              <li><strong>Portability:</strong> Export your generated documents at any time.</li>
            </ul>
            <p className="mt-3">
              To exercise these rights, email us at{" "}
              <a href="mailto:privacy@hirestack.tech" className="text-primary underline">
                privacy@hirestack.tech
              </a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Cookies</h2>
            <p>
              We use only essential cookies required for authentication (session tokens). We do not use
              tracking or advertising cookies.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">8. Third-party services</h2>
            <p>We use the following third-party services:</p>
            <ul className="list-disc pl-5 space-y-1 mt-2">
              <li><strong>Supabase</strong> — Authentication and database</li>
              <li><strong>Google Gemini API</strong> — AI document generation</li>
              <li><strong>Stripe</strong> — Payment processing (for paid plans)</li>
              <li><strong>Sentry</strong> — Error monitoring</li>
            </ul>
            <p className="mt-2">Each provider has its own privacy policy governing their data handling.</p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">9. Data retention</h2>
            <p>
              We retain your data for as long as your account is active. Deleted accounts have their data
              purged within 30 days. Anonymised aggregate usage statistics may be retained indefinitely.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">10. Changes to this policy</h2>
            <p>
              We may update this policy from time to time. Significant changes will be communicated via
              email or an in-app notice. Continued use of the service after changes constitutes acceptance.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">11. Contact</h2>
            <p>
              For any privacy-related questions, contact us at{" "}
              <a href="mailto:privacy@hirestack.tech" className="text-primary underline">
                privacy@hirestack.tech
              </a>.
            </p>
          </section>
        </div>

        <div className="mt-16 border-t pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
          <p>© {new Date().getFullYear()} HireStack AI. All rights reserved.</p>
          <div className="flex gap-4">
            <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
          </div>
        </div>
      </main>
    </div>
  );
}
