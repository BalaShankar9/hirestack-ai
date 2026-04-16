"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import type { User, Session } from "@supabase/supabase-js";
import { ThemeProvider } from "next-themes";
import { supabase } from "@/lib/supabase";
import { installGlobalErrorHandler } from "@/lib/error-reporting";
import { checkEnvOnce } from "@/lib/env-validation";

/* ------------------------------------------------------------------ */
/*  Auth context types                                                */
/* ------------------------------------------------------------------ */

export interface AuthUser {
  uid: string;
  id: string;
  email: string | null;
  displayName: string | null;
  full_name: string | null;
  photoURL: string | null;
  user_metadata?: Record<string, any>;
}

interface AuthContextValue {
  user: AuthUser | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name?: string) => Promise<void>;
  signOut: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signInWithGitHub: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  session: null,
  loading: true,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  signInWithGoogle: async () => {},
  signInWithGitHub: async () => {},
});

/* ------------------------------------------------------------------ */
/*  Map Supabase User → AuthUser                                      */
/* ------------------------------------------------------------------ */

function mapUser(u: User | null): AuthUser | null {
  if (!u) return null;
  return {
    uid: u.id,
    id: u.id,
    email: u.email ?? null,
    displayName: u.user_metadata?.full_name ?? u.user_metadata?.name ?? null,
    full_name: u.user_metadata?.full_name ?? null,
    photoURL: u.user_metadata?.avatar_url ?? null,
    user_metadata: u.user_metadata,
  };
}

/* ------------------------------------------------------------------ */
/*  Provider                                                           */
/* ------------------------------------------------------------------ */

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    installGlobalErrorHandler();
    checkEnvOnce();
  }, []);

  useEffect(() => {
    // Get initial session with timeout + retry
    let cancelled = false;

    async function loadSession() {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const { data: { session: s } } = await Promise.race([
            supabase.auth.getSession(),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error("Timeout")), attempt === 0 ? 5000 : 8000)
            ),
          ]);
          if (cancelled) return;
          supabase.realtime.setAuth(s?.access_token ?? "");
          setSession(s);
          setUser(mapUser(s?.user ?? null));
          setLoading(false);
          return;
        } catch (err) {
          if (cancelled) return;
          if (attempt === 0) {
            console.warn("Supabase getSession attempt 1 failed, retrying…", err);
            continue;
          }
          console.error("Supabase getSession failed after retry:", err);
          setLoading(false);
        }
      }
    }

    loadSession();

    // Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, s) => {
      supabase.realtime.setAuth(s?.access_token ?? "");
      setSession(s);
      setUser(mapUser(s?.user ?? null));
      setLoading(false);

      // Handle session expiry — redirect to login when signed out unexpectedly
      if (event === "SIGNED_OUT" && typeof window !== "undefined") {
        // Only redirect if we're on a protected page (not login or landing)
        const path = window.location.pathname;
        if (path !== "/" && path !== "/login" && !path.startsWith("/auth")) {
          window.location.href = "/login?expired=1";
        }
      }

      // Handle token refresh failure — session is now invalid
      if (event === "TOKEN_REFRESHED" && !s) {
        setUser(null);
        setSession(null);
        if (typeof window !== "undefined") {
          const path = window.location.pathname;
          if (path !== "/" && path !== "/login" && !path.startsWith("/auth")) {
            window.location.href = "/login?expired=1";
          }
        }
      }
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await Promise.race([
      supabase.auth.signInWithPassword({ email, password }),
      new Promise<any>((_, reject) => setTimeout(() => reject(new Error("Network timeout: Auth server is unreachable.")), 8000))
    ]);
    if (error) throw error;
  }, []);

  const signUp = useCallback(
    async (email: string, password: string, name?: string) => {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: name ?? "" } },
      });
      if (error) throw error;
      // If user already exists, signUp returns a user with no session
      // In that case, try signing in instead
      if (data?.user && !data?.session) {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) throw new Error("Account exists. Please sign in instead.");
      }
    },
    []
  );

  const signOut = useCallback(async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) throw error;
  }, []);

  const signInWithGitHub = useCallback(async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) throw error;
  }, []);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <AuthContext.Provider
        value={{
          user,
          session,
          loading,
          signIn,
          signUp,
          signOut,
          signInWithGoogle,
          signInWithGitHub,
        }}
      >
        {children}
      </AuthContext.Provider>
    </ThemeProvider>
  );
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

/** Alias so layout.tsx can import { Providers } */
export const Providers = AuthProvider;
