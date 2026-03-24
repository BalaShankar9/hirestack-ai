/**
 * Supabase Client — Single shared instance for the frontend.
 *
 * Exports:
 *  - supabase  — The Supabase client (public / anon key)
 *  - supabaseAuth — shorthand for supabase.auth
 */
"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://placeholder.supabase.co";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "placeholder";

const IS_CONFIGURED = !!(
  process.env.NEXT_PUBLIC_SUPABASE_URL &&
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

if (!IS_CONFIGURED && typeof window !== "undefined") {
  console.warn(
    "[HireStack] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY not set — Supabase calls will fail."
  );
}

function createSupabaseClient(): SupabaseClient {
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
    realtime: {
      timeout: 30_000,
    },
  });
}

type GlobalWithSupabase = typeof globalThis & {
  __hirestackSupabase?: SupabaseClient;
};

const globalForSupabase = globalThis as GlobalWithSupabase;

// In dev, Fast Refresh can re-evaluate modules; keep a singleton client to prevent
// multiple concurrent Realtime sockets and flapping subscriptions.
export const supabase: SupabaseClient =
  globalForSupabase.__hirestackSupabase ?? createSupabaseClient();

if (process.env.NODE_ENV !== "production") {
  globalForSupabase.__hirestackSupabase = supabase;
}

if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
  (window as any).__hirestackSupabase = supabase;
}

export const supabaseAuth = supabase.auth;
