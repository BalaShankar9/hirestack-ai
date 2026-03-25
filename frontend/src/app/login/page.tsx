"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Sparkles, ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "@/components/providers";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    }>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { signIn, signUp, signInWithGoogle, signInWithGitHub } = useAuth();

  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<"google" | "github" | null>(null);

  // Read ?mode=register from URL so "Get Started" links land on sign-up
  useEffect(() => {
    if (searchParams.get("mode") === "register") {
      setIsRegister(true);
    }
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isRegister) {
        await signUp(email, password, name);
      } else {
        await signIn(email, password);
      }
      // Small delay to let auth state propagate before redirect
      const redirect = searchParams.get("redirect") || "/dashboard";
      await new Promise((r) => setTimeout(r, 500));
      window.location.href = redirect;
    } catch (err: any) {
      setError(err?.message ?? "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleOAuth(provider: "google" | "github") {
    setError(null);
    setOauthLoading(provider);
    try {
      if (provider === "google") await signInWithGoogle();
      else await signInWithGitHub();
    } catch (err: any) {
      setError(err?.message ?? "OAuth sign-in failed");
      setOauthLoading(null);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* ── Left: Branding Panel ──────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary via-violet-600 to-indigo-700">
        {/* Background decoration */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-20 -top-20 h-[400px] w-[400px] rounded-full border-[50px] border-white/5" />
          <div className="absolute -bottom-20 -left-20 h-[300px] w-[300px] rounded-full border-[40px] border-white/5" />
          <div className="absolute right-1/4 top-1/3 h-[200px] w-[200px] rounded-full bg-white/5 blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col justify-between p-12">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 backdrop-blur-sm">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <span className="text-lg font-bold text-white tracking-tight">
              HireStack AI
            </span>
          </Link>

          <div className="max-w-md">
            <h2 className="text-3xl font-bold text-white leading-tight">
              Your next role starts with a smarter application
            </h2>
            <p className="mt-4 text-base text-white/70 leading-relaxed">
              Benchmark → Analyze → Build proof → Ship. Our AI-powered system
              turns job descriptions into actionable improvement plans with
              evidence-backed documents.
            </p>

            {/* Social proof */}
            <div className="mt-10 grid grid-cols-3 gap-4">
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm">
                <div className="text-2xl font-bold text-white">6</div>
                <div className="text-[11px] text-white/60">AI modules</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm">
                <div className="text-2xl font-bold text-white">94%</div>
                <div className="text-[11px] text-white/60">keyword coverage</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm">
                <div className="text-2xl font-bold text-white">5 min</div>
                <div className="text-[11px] text-white/60">to first result</div>
              </div>
            </div>
          </div>

          <p className="text-xs text-white/40">
            © {new Date().getFullYear()} HireStack AI
          </p>
        </div>
      </div>

      {/* ── Right: Auth Form ──────────────────────── */}
      <div className="flex w-full flex-col items-center justify-center px-4 lg:w-1/2">
        {/* Mobile logo */}
        <Link href="/" className="mb-8 flex items-center gap-2.5 lg:hidden">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-glow-sm">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight">
            HireStack <span className="text-primary">AI</span>
          </span>
        </Link>

        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold tracking-tight">
              {isRegister ? "Create your account" : "Welcome back"}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {isRegister
                ? "Start building better applications today"
                : "Sign in to continue to your workspace"}
            </p>
          </div>

          {/* OAuth — hidden until configured */}

          {/* Divider - hidden when OAuth is hidden */}

          {/* Email form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <div className="space-y-2">
                <Label htmlFor="name" className="text-xs font-medium">Full Name</Label>
                <Input
                  id="name"
                  placeholder="Jane Doe"
                  className="rounded-xl h-11"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="email" className="text-xs font-medium">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                required
                className="rounded-xl h-11"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-xs font-medium">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                required
                minLength={6}
                className="rounded-xl h-11"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="rounded-xl bg-destructive/10 border border-destructive/20 p-3"
              >
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-11 rounded-xl gap-2 bg-primary shadow-glow-sm hover:shadow-glow-md transition-all"
              disabled={loading || oauthLoading !== null}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Please wait…
                </>
              ) : isRegister ? (
                <>
                  Create Account
                  <ArrowRight className="h-4 w-4" />
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isRegister ? "Already have an account?" : "Don't have an account?"}{" "}
            <button
              className="font-medium text-primary hover:text-primary/80 transition-colors"
              onClick={() => {
                setIsRegister(!isRegister);
                setError(null);
              }}
              type="button"
            >
              {isRegister ? "Sign In" : "Create Account"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
