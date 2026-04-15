"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Sparkles, ArrowRight, Loader2, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/components/providers";
import { supabase } from "@/lib/supabase";
import { useToast } from "@/hooks/use-toast";

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
  const [showPassword, setShowPassword] = useState(false);
  const [checkEmail, setCheckEmail] = useState(false);
  const { toast } = useToast();

  // Read ?mode=register from URL so "Get Started" links land on sign-up
  useEffect(() => {
    if (searchParams.get("mode") === "register") {
      setIsRegister(true);
    }
    // Show session expired message if redirected from auth expiry
    if (searchParams.get("expired") === "1") {
      setError("Your session has expired. Please sign in again.");
      toast({
        title: "Session Expired",
        description: "Your session has expired. Please sign in again.",
        variant: "error",
      });
    }
  }, [searchParams, toast]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isRegister) {
        await signUp(email, password, name);
        // After sign-up, show "check your email" screen instead of polling for session,
        // since Supabase sends a confirmation email before activating the account.
        setCheckEmail(true);
        setLoading(false);
        return;
      } else {
        await signIn(email, password);
      }
      // Poll for session with backoff instead of fixed 800ms wait
      const redirect = searchParams.get("redirect") || "/dashboard";
      let sessionFound = false;
      for (let attempt = 0; attempt < 10; attempt++) {
        const { data: { session: s } } = await supabase.auth.getSession();
        if (s?.access_token) { sessionFound = true; break; }
        await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
      }
      if (sessionFound) {
        window.location.href = redirect;
      } else {
        setError("Session not established. Please refresh and try again.");
      }
    } catch (err: any) {
      const msg = err?.message ?? "Authentication failed";
      let finalMsg = msg;
      if (msg.toLowerCase().includes("failed to fetch") || msg.toLowerCase().includes("network")) {
        finalMsg = "Unable to reach the authentication server. Please check your internet connection and try again.";
      } else if (msg.toLowerCase().includes("invalid") && !isRegister) {
        finalMsg = "Invalid credentials. Don't have an account yet? Click 'Create Account' below.";
      }
      setError(finalMsg);
      toast({
        title: "Authentication Failed",
        description: finalMsg,
      });
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
      const msg = err?.message ?? "OAuth sign-in failed";
      setError(msg);
      toast({
        title: "Authentication Failed",
        description: msg,
      });
      setOauthLoading(null);
    }
  }

  if (checkEmail) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 bg-gradient-to-br from-primary via-violet-600 to-indigo-700">
        <div className="w-full max-w-sm rounded-2xl bg-white/10 backdrop-blur-md border border-white/20 p-8 text-center text-white">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/20">
            <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold">Check your email</h2>
          <p className="mt-3 text-sm text-white/75 leading-relaxed">
            We sent a confirmation link to <strong className="text-white">{email}</strong>.
            Click the link to activate your account and get started.
          </p>
          <p className="mt-4 text-xs text-white/50">
            Didn&apos;t receive it? Check your spam folder, or{" "}
            <button
              type="button"
              className="underline text-white/70 hover:text-white transition-colors"
              onClick={() => { setCheckEmail(false); setIsRegister(true); }}
            >
              try again
            </button>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      {/* ── Left: Branding Panel ──────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary via-violet-600 to-indigo-700">
        {/* Aurora ambient background */}
        <div className="aurora-bg" aria-hidden="true" />
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
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm glass-depth">
                <div className="text-2xl font-bold text-white">6</div>
                <div className="text-[11px] text-white/60">AI modules</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm glass-depth">
                <div className="text-2xl font-bold text-white">94%</div>
                <div className="text-[11px] text-white/60">keyword coverage</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3 backdrop-blur-sm glass-depth">
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
      <div className="flex w-full flex-col items-center justify-center px-4 lg:w-1/2 noise-overlay">
        {/* Mobile logo */}
        <Link href="/" className="mb-8 flex items-center gap-2.5 lg:hidden">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet-600 btn-glow">
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

          {/* OAuth */}
          <div className="grid grid-cols-2 gap-3">
            <Button
              variant="outline"
              className="rounded-xl h-11"
              onClick={() => handleOAuth("google")}
              disabled={loading || oauthLoading !== null}
            >
              {oauthLoading === "google" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
              )}
              Google
            </Button>
            <Button
              variant="outline"
              className="rounded-xl h-11"
              onClick={() => handleOAuth("github")}
              disabled={loading || oauthLoading !== null}
            >
              {oauthLoading === "github" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
              )}
              GitHub
            </Button>
          </div>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center"><span className="w-full border-t" /></div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">or continue with email</span>
            </div>
          </div>

          {/* Email form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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
                className="rounded-xl h-11"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-xs font-medium">Password</Label>
                {!isRegister && (
                  <button
                    type="button"
                    className="text-xs text-primary hover:text-primary/80 transition-colors"
                    onClick={async () => {
                      if (!email) { setError("Enter your email first"); return; }
                      try {
                        await supabase.auth.resetPasswordForEmail(email, {
                          redirectTo: `${window.location.origin}/auth/reset-password`,
                        });
                        setError(null);
                        toast({ title: "Reset Email Sent", description: "Check your inbox for a password reset link." });
                      } catch (e: any) { setError(e.message); }
                    }}
                  >
                    Forgot password?
                  </button>
                )}
              </div>
              <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                className="rounded-xl h-11 pr-10"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                tabIndex={-1}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
              </div>
              {isRegister && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  Minimum 8 characters. Use a mix of letters, numbers, and symbols for a stronger password.
                </p>
              )}
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
              className="w-full h-11 rounded-xl gap-2 bg-primary btn-glow transition-all"
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
