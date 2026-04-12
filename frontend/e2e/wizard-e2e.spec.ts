/**
 * HireStack AI — Real E2E Wizard Flow
 *
 * Tests the complete user journey: login → dashboard → new application wizard.
 * Uses a REAL Supabase user and the actual login form.
 *
 * Requires env vars:
 *   E2E_TEST_EMAIL        (default: e2e-test@hirestack.local)
 *   E2E_TEST_PASSWORD     (default: E2ETestPass!2026)
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 *
 * Run:
 *   npx playwright test e2e/wizard-e2e.spec.ts --project=chromium
 */
import { test, expect, type Page } from "@playwright/test";

const E2E_EMAIL = process.env.E2E_TEST_EMAIL || "e2e-test@hirestack.local";
const E2E_PASSWORD = process.env.E2E_TEST_PASSWORD || "E2ETestPass!2026";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

const SAMPLE_JD = `We are looking for a Senior Python Engineer with 5+ years of experience
building scalable backend services. Must have strong experience with
FastAPI, PostgreSQL, and cloud platforms (AWS/GCP). Experience with
AI/ML pipelines is a strong plus. You will lead a team of 3 engineers
and report to the VP of Engineering.`;

const SAMPLE_RESUME = `Jane Doe — Senior Software Engineer
5 years at TechCorp building Python microservices on AWS.
Led migration from monolith to FastAPI-based microservices.
Reduced API latency by 40% through async optimization.
Built ML inference pipeline serving 10K req/s.
BSc Computer Science, MIT 2019.
Skills: Python, FastAPI, PostgreSQL, AWS, Docker, Kubernetes,
TensorFlow, Redis, CI/CD, Agile.`;

// ── Helpers ─────────────────────────────────────────────────────────

/**
 * Sign in via the Supabase client in the browser (after navigating to /login
 * so the client is loaded). Then navigate to the target page.
 */
async function signInViaBrowser(page: Page, targetUrl = "/dashboard"): Promise<void> {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");

  const result = await page.evaluate(
    async ({ email, password }: { email: string; password: string }) => {
      const sb = (window as any).__hirestackSupabase;
      if (!sb) return { error: "supabase client not found on window" };
      const { data, error } = await sb.auth.signInWithPassword({ email, password });
      if (error) return { error: error.message };
      return { ok: true, email: data.user?.email };
    },
    { email: E2E_EMAIL, password: E2E_PASSWORD }
  );

  if ((result as any).error) {
    throw new Error(`Browser sign-in failed: ${(result as any).error}`);
  }

  await page.goto(targetUrl);
}

/**
 * Sign in via the login form (the real user flow).
 */
async function signInViaForm(page: Page): Promise<void> {
  await page.goto("/login");
  await expect(page.locator("#email")).toBeVisible({ timeout: 10000 });
  await page.locator("#email").fill(E2E_EMAIL);
  await page.locator("#password").fill(E2E_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/dashboard/, { timeout: 25000 });
}

// ── Skip check ──────────────────────────────────────────────────────

test.beforeEach(async () => {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    test.skip(true, "Missing NEXT_PUBLIC_SUPABASE_URL or ANON_KEY");
  }
});

// ═══════════════════════════════════════════════════════════════════════
// TEST 1: Login form works end-to-end
// ═══════════════════════════════════════════════════════════════════════

test.describe("Real Auth Flow", () => {
  test("login form signs in and redirects to dashboard", async ({ page }) => {
    await signInViaForm(page);

    await expect(page.locator(".animate-spin")).not.toBeVisible({ timeout: 10000 });

    await expect(page.locator("body")).toContainText(/New Application|Overview|HireStack/i, {
      timeout: 5000,
    });
  });

  test("login page renders and accepts input", async ({ page }) => {
    await page.goto("/login");

    await expect(page.locator("#email")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /Sign In/i })).toBeVisible();

    await page.locator("#email").fill(E2E_EMAIL);
    await page.locator("#password").fill(E2E_PASSWORD);
    await expect(page.locator("#email")).toHaveValue(E2E_EMAIL);
    await expect(page.locator("#password")).toHaveValue(E2E_PASSWORD);
  });

  test("authenticated API session + backend health check", async ({ page }) => {
    const resp = await page.request.post(
      `${SUPABASE_URL}/auth/v1/token?grant_type=password`,
      {
        headers: {
          apikey: SUPABASE_ANON_KEY,
          "Content-Type": "application/json",
        },
        data: { email: E2E_EMAIL, password: E2E_PASSWORD },
      }
    );

    expect(resp.ok()).toBe(true);
    const session = await resp.json();
    expect(session.access_token).toBeTruthy();
    expect(session.user.email).toBe(E2E_EMAIL);

    const healthResp = await page.request.get("http://127.0.0.1:8000/health");
    expect(healthResp.ok()).toBe(true);
    const health = await healthResp.json();
    expect(health.status).toBe("healthy");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// TEST 2: Dashboard loads with real content
// ═══════════════════════════════════════════════════════════════════════

test.describe("Dashboard", () => {
  test("dashboard shows navigation and content", async ({ page }) => {
    await signInViaBrowser(page, "/dashboard");

    await expect(page.locator(".animate-spin")).not.toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: "New Application" })).toBeVisible({ timeout: 5000 });

    const body = await page.textContent("body");
    expect(body).toContain("HireStack");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// TEST 3: New Application Wizard
// ═══════════════════════════════════════════════════════════════════════

test.describe("New Application Wizard", () => {
  test("can navigate to /new and see the wizard form", async ({ page }) => {
    await signInViaBrowser(page, "/new");
    await expect(page.locator(".animate-spin")).not.toBeVisible({ timeout: 10000 });

    const body = await page.textContent("body");
    const hasWizardContent =
      body?.includes("Job") ||
      body?.includes("job") ||
      body?.includes("Step") ||
      body?.includes("Title") ||
      body?.includes("Description") ||
      body?.includes("Paste");
    expect(hasWizardContent).toBe(true);
  });

  test("can fill job details in step 1", async ({ page }) => {
    await signInViaBrowser(page, "/new");
    await expect(page.locator(".animate-spin")).not.toBeVisible({ timeout: 10000 });

    const jobTitleInput = page
      .getByPlaceholder(/job title/i)
      .or(page.locator('input[name="jobTitle"]'))
      .or(page.locator('input[name="job_title"]'));

    const jdTextarea = page
      .getByPlaceholder(/paste.*description|job.*description/i)
      .or(page.locator('textarea[name="jdText"]'))
      .or(page.locator('textarea[name="jd_text"]'))
      .or(page.locator("textarea").first());

    const hasJobTitle = await jobTitleInput.isVisible({ timeout: 5000 }).catch(() => false);
    const hasJdTextarea = await jdTextarea.isVisible({ timeout: 5000 }).catch(() => false);

    expect(hasJobTitle || hasJdTextarea).toBe(true);

    if (hasJobTitle) {
      await jobTitleInput.fill("Senior Python Engineer");
      await expect(jobTitleInput).toHaveValue("Senior Python Engineer");
    }

    if (hasJdTextarea) {
      await jdTextarea.fill(SAMPLE_JD);
      const value = await jdTextarea.inputValue();
      expect(value.length).toBeGreaterThan(50);
    }
  });
});
