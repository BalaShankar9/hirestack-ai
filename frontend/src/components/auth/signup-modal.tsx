"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/components/providers";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import {
  Loader2,
  ArrowRight,
  FileText,
  Shield,
  Zap,
  Users,
  Check,
} from "lucide-react";

interface SignupModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  documentName?: string;
}

const SOCIAL_PROOF = [
  { icon: Users, text: "10,000+ professionals" },
  { icon: Shield, text: "Bank-level security" },
  { icon: Zap, text: "5 free downloads" },
];

export function SignupModal({ open, onOpenChange, onSuccess, documentName }: SignupModalProps) {
  const { signIn, signUp, signInWithGoogle, signInWithGitHub } = useAuth();
  const [step, setStep] = useState<"main" | "email">("main");
  const [isRegister, setIsRegister] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<"google" | "github" | null>(null);
  const [success, setSuccess] = useState(false);

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
      await new Promise((r) => setTimeout(r, 600));
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        setSuccess(true);
        setTimeout(() => {
          onOpenChange(false);
          onSuccess?.();
          // Reset state after close
          setTimeout(() => { setSuccess(false); setStep("main"); }, 300);
        }, 1200);
      } else {
        setError("Check your email for a confirmation link.");
      }
    } catch (err: any) {
      const msg = err?.message ?? "Authentication failed";
      if (msg.toLowerCase().includes("invalid") && !isRegister) {
        setError("Invalid credentials. Try creating an account instead.");
      } else if (msg.toLowerCase().includes("already registered")) {
        setError("Account exists — switching to sign in.");
        setIsRegister(false);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleOAuth(provider: "google" | "github") {
    setError(null);
    setOauthLoading(provider);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("hirestack_return_to", window.location.pathname + window.location.search);
    }
    try {
      if (provider === "google") await signInWithGoogle();
      else await signInWithGitHub();
    } catch (err: any) {
      setError(err?.message ?? "OAuth sign-in failed");
      setOauthLoading(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg p-0 overflow-hidden border-0 shadow-2xl">
        <AnimatePresence mode="wait">
          {success ? (
            /* ── Success State ── */
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center justify-center py-16 px-8"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 300, damping: 15, delay: 0.1 }}
                className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 shadow-glow-md"
              >
                <Check className="h-8 w-8 text-white" />
              </motion.div>
              <motion.h3
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="mt-4 text-lg font-bold"
              >
                Welcome to HireStack!
              </motion.h3>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="mt-1 text-sm text-muted-foreground"
              >
                Starting your download...
              </motion.p>
            </motion.div>
          ) : (
            /* ── Main Content ── */
            <motion.div
              key={step}
              initial={{ opacity: 0, x: step === "email" ? 20 : 0 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {/* Gradient header with document preview */}
              <div className="relative bg-gradient-to-br from-primary/10 via-violet-500/5 to-transparent px-6 pt-8 pb-6">
                {/* Floating document preview */}
                <div className="absolute right-6 top-4 opacity-[0.08]">
                  <FileText className="h-24 w-24" />
                </div>
                <div className="relative">
                  <div className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-[10px] font-semibold text-primary uppercase tracking-wider mb-3">
                    <Zap className="h-3 w-3" /> Almost there
                  </div>
                  <h2 className="text-xl font-bold tracking-tight">
                    {documentName
                      ? `Download your ${documentName}`
                      : "Download your documents"}
                  </h2>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Create a free account to download — takes 10 seconds.
                  </p>
                </div>
              </div>

              <div className="px-6 pb-6">
                {step === "main" ? (
                  /* ── Main: OAuth + Email option ── */
                  <div className="space-y-3 mt-4">
                    {/* Google — Primary CTA (largest, most prominent) */}
                    <Button
                      className="w-full h-12 rounded-xl gap-3 text-sm font-semibold bg-white hover:bg-gray-50 text-gray-800 border shadow-sm transition-all hover:shadow-md"
                      onClick={() => handleOAuth("google")}
                      disabled={loading || oauthLoading !== null}
                    >
                      {oauthLoading === "google" ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <svg className="h-5 w-5" viewBox="0 0 24 24">
                          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                        </svg>
                      )}
                      Continue with Google
                    </Button>

                    {/* GitHub — Secondary */}
                    <Button
                      variant="outline"
                      className="w-full h-11 rounded-xl gap-3 text-sm"
                      onClick={() => handleOAuth("github")}
                      disabled={loading || oauthLoading !== null}
                    >
                      {oauthLoading === "github" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                        </svg>
                      )}
                      Continue with GitHub
                    </Button>

                    {/* Email option — tertiary */}
                    <button
                      className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors py-2"
                      onClick={() => setStep("email")}
                    >
                      Or use email &amp; password →
                    </button>

                    {/* Social proof strip */}
                    <div className="flex items-center justify-center gap-4 pt-3 border-t mt-2">
                      {SOCIAL_PROOF.map((item, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <item.icon className="h-3 w-3 text-primary/60" />
                          {item.text}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  /* ── Email Form ── */
                  <div className="mt-4">
                    <button
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-4 transition-colors"
                      onClick={() => { setStep("main"); setError(null); }}
                    >
                      ← Back to sign in options
                    </button>

                    <form onSubmit={handleSubmit} className="space-y-3">
                      {isRegister && (
                        <div className="space-y-1">
                          <Label htmlFor="modal-name" className="text-xs">Name</Label>
                          <Input id="modal-name" placeholder="Jane Doe" className="rounded-xl h-10"
                            value={name} onChange={(e) => setName(e.target.value)} />
                        </div>
                      )}
                      <div className="space-y-1">
                        <Label htmlFor="modal-email" className="text-xs">Email</Label>
                        <Input id="modal-email" type="email" placeholder="you@example.com" required className="rounded-xl h-10"
                          value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="modal-password" className="text-xs">Password</Label>
                        <Input id="modal-password" type="password" placeholder="6+ characters" required minLength={6} className="rounded-xl h-10"
                          value={password} onChange={(e) => setPassword(e.target.value)} />
                      </div>

                      <AnimatePresence>
                        {error && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="rounded-xl bg-destructive/10 border border-destructive/20 p-2.5"
                          >
                            <p className="text-xs text-destructive">{error}</p>
                          </motion.div>
                        )}
                      </AnimatePresence>

                      <Button type="submit" className="w-full h-11 rounded-xl gap-2 shadow-glow-sm" disabled={loading}>
                        {loading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <ArrowRight className="h-4 w-4" />
                        )}
                        {isRegister ? "Create Free Account" : "Sign In"}
                      </Button>

                      <p className="text-center text-xs text-muted-foreground">
                        {isRegister ? "Already have an account?" : "Need an account?"}{" "}
                        <button className="font-medium text-primary hover:text-primary/80" type="button"
                          onClick={() => { setIsRegister(!isRegister); setError(null); }}>
                          {isRegister ? "Sign In" : "Create Account"}
                        </button>
                      </p>
                    </form>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  );
}
