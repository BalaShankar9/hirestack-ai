/**
 * S8-F2: Behavioural pinning for src/lib/env-validation.ts.
 *
 * The module captures `process.env.NEXT_PUBLIC_*` literals at IMPORT
 * time into a private ENV_VALUES map (Next.js does static replacement
 * of literal references only — dynamic access doesn't work in
 * production). To exercise different env shapes we therefore use
 * vi.stubEnv + vi.resetModules + dynamic `await import(...)` per test.
 *
 * The vitest config (vitest.config.ts) seeds NEXT_PUBLIC_SUPABASE_URL
 * and friends to placeholder values, so the "happy path" baseline is
 * tested as well as the missing/invalid branches.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

const VALID_URL = "https://placeholder.supabase.co";
const VALID_KEY = "x".repeat(50);
const VALID_API = "http://localhost:8000";

async function loadFresh() {
  vi.resetModules();
  return await import("@/lib/env-validation");
}

describe("validateEnv", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("returns {valid: true, errors: [], warnings: []} on the SSR path (no window)", async () => {
    const original = globalThis.window;
    // @ts-expect-error — intentionally removing for the SSR-path test.
    delete globalThis.window;
    try {
      const mod = await loadFresh();
      expect(mod.validateEnv()).toEqual({ valid: true, errors: [], warnings: [] });
    } finally {
      // @ts-expect-error — restoring.
      globalThis.window = original;
    }
  });

  it("returns valid=true with no errors when all required vars are set correctly", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", VALID_API);
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(true);
    expect(r.errors).toEqual([]);
  });

  it("emits an error when NEXT_PUBLIC_SUPABASE_URL is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(false);
    expect(r.errors).toContain("Missing required env var: NEXT_PUBLIC_SUPABASE_URL");
  });

  it("emits an error when NEXT_PUBLIC_SUPABASE_ANON_KEY is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(false);
    expect(r.errors).toContain("Missing required env var: NEXT_PUBLIC_SUPABASE_ANON_KEY");
  });

  it("rejects NEXT_PUBLIC_SUPABASE_URL that does not start with https://", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "http://insecure.example.com");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(false);
    expect(r.errors).toContain("NEXT_PUBLIC_SUPABASE_URL must start with https://");
  });

  it("rejects an anon key that is 20 chars or shorter (boundary)", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "x".repeat(20));
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(false);
    expect(r.errors).toContain(
      "NEXT_PUBLIC_SUPABASE_ANON_KEY looks too short — is it correct?",
    );
  });

  it("accepts an anon key that is 21 chars (just past boundary)", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "x".repeat(21));
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(true);
  });

  it("treats NEXT_PUBLIC_API_URL as optional — missing produces a WARNING not an error", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(true);
    expect(r.warnings).toContain("Optional env var not set: NEXT_PUBLIC_API_URL");
  });

  it("warns (not errors) when NEXT_PUBLIC_API_URL has an invalid scheme", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "ftp://example.com");
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.valid).toBe(true);
    expect(r.warnings).toContain(
      "NEXT_PUBLIC_API_URL must start with http:// or https://",
    );
  });

  it("accepts NEXT_PUBLIC_API_URL with http://", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.example.com");
    const mod = await loadFresh();
    expect(mod.validateEnv().warnings).toEqual([]);
  });

  it("accepts NEXT_PUBLIC_API_URL with https://", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    const mod = await loadFresh();
    expect(mod.validateEnv().warnings).toEqual([]);
  });

  it("aggregates multiple errors when several required vars fail", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    const mod = await loadFresh();
    const r = mod.validateEnv();
    expect(r.errors.length).toBeGreaterThanOrEqual(2);
    expect(r.valid).toBe(false);
  });
});

describe("checkEnvOnce", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.unstubAllEnvs();
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("logs an error to console.error when validation fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    const mod = await loadFresh();
    mod.checkEnvOnce();
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    const msg = consoleErrorSpy.mock.calls[0][0] as string;
    expect(msg).toContain("Environment misconfiguration");
    expect(msg).toContain("frontend/.env.example");
  });

  it("does NOT log when validation passes cleanly", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", VALID_API);
    const mod = await loadFresh();
    mod.checkEnvOnce();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });

  it("memoises — the second call is a no-op (no duplicate logs)", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    const mod = await loadFresh();
    mod.checkEnvOnce();
    mod.checkEnvOnce();
    mod.checkEnvOnce();
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
  });

  it("is a no-op on the SSR path (no window)", async () => {
    const original = globalThis.window;
    // @ts-expect-error — intentionally removing for the SSR-path test.
    delete globalThis.window;
    try {
      const mod = await loadFresh();
      mod.checkEnvOnce();
      expect(consoleErrorSpy).not.toHaveBeenCalled();
    } finally {
      // @ts-expect-error — restoring.
      globalThis.window = original;
    }
  });

  it("emits warnings to console.warn in non-production when warnings are present", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    const mod = await loadFresh();
    mod.checkEnvOnce();
    expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
    expect(consoleWarnSpy.mock.calls[0][0]).toContain("Environment warnings");
  });

  it("suppresses warnings in production NODE_ENV", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", VALID_URL);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", VALID_KEY);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    const mod = await loadFresh();
    mod.checkEnvOnce();
    expect(consoleWarnSpy).not.toHaveBeenCalled();
  });
});
