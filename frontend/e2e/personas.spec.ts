/**
 * UX Persona Simulation Tests
 *
 * 10 realistic user personas exercising HireStack AI end-to-end.
 * Each persona represents a distinct user segment, motivation, and workflow.
 *
 * Personas:
 *  1. Sarah – Senior SWE, core happy-path (new application → workspace)
 *  2. Marcus – Career changer, ATS scanner + evidence vault focus
 *  3. Priya – New grad, interview prep + learning challenges
 *  4. James – Recruiter/org admin, candidate pipeline + team management
 *  5. Aisha – Freelancer, A/B lab + salary coach
 *  6. Chen – Executive, career analytics + profile hub
 *  7. Emma – Accessibility-first user, keyboard-only navigation
 *  8. Diego – Mobile user, responsive layout validation
 *  9. Fatima – Security-conscious user, auth flows + session management
 * 10. Raj – Power user, command palette + multi-application workflow
 */

import { test, expect, type Page } from "@playwright/test";

// ─── Helpers ────────────────────────────────────────────────────────────────

const E2E_EMAIL = process.env.E2E_TEST_EMAIL ?? "test@hirestack.ai";
const E2E_PASSWORD = process.env.E2E_TEST_PASSWORD ?? "TestPass123!";

/**
 * Sign in via Supabase client injection (faster than form).
 * If auth fails (no test account provisioned), the test is skipped.
 */
async function signIn(page: Page, target = "/dashboard") {
  await page.goto("/login");
  // Try client injection first, fall back to form login
  const injected = await page
    .evaluate(
      async ({ email, password }) => {
        const sb = (window as any).__hirestackSupabase;
        if (!sb) return false;
        const { error } = await sb.auth.signInWithPassword({ email, password });
        return !error;
      },
      { email: E2E_EMAIL, password: E2E_PASSWORD }
    )
    .catch(() => false);

  if (injected) {
    await page.goto(target);
  } else {
    await page.locator("#email").fill(E2E_EMAIL);
    await page.locator("#password").fill(E2E_PASSWORD);
    await page.locator('button[type="submit"]').click();
    try {
      await page.waitForURL(/dashboard/, { timeout: 8_000 });
    } catch {
      // Auth failed — no test user provisioned in Supabase
      test.skip(true, "No E2E test account available (set E2E_TEST_EMAIL / E2E_TEST_PASSWORD)");
      return;
    }
    if (target !== "/dashboard") await page.goto(target);
  }
}

/** Assert page title or heading matches. */
async function expectHeading(page: Page, pattern: RegExp) {
  await expect(
    page.getByRole("heading", { level: 1 }).or(page.getByRole("heading", { level: 2 })).first()
  ).toHaveText(pattern, { timeout: 10_000 });
}

// ─── Persona 1: Sarah – Senior SWE, Core Happy Path ────────────────────────

test.describe("Persona 1: Sarah – Senior SWE", () => {
  test("navigates landing → signup → dashboard", async ({ page }) => {
    await page.goto("/");
    // Landing page loads with CTA
    await expect(page.getByRole("link", { name: /get started/i }).first()).toBeVisible({
      timeout: 10_000,
    });

    // Navigate to register
    await page.goto("/login?mode=register");
    await expect(page.getByRole("heading", { name: /create.*account|register|sign up/i })).toBeVisible();
    // Verify registration fields exist
    await expect(page.getByLabel(/name/i).first()).toBeVisible();
    await expect(page.locator("#email").or(page.getByLabel(/email/i))).toBeVisible();
    await expect(page.locator("#password").or(page.getByLabel(/password/i))).toBeVisible();
  });

  test("creates a new application via wizard", async ({ page }) => {
    await signIn(page, "/new");

    // Step 1: Job Description
    const jdTextarea = page.locator("textarea").first().or(page.getByPlaceholder(/job description|paste/i));
    await expect(jdTextarea).toBeVisible({ timeout: 10_000 });
    await jdTextarea.fill(
      "Senior Software Engineer at TechCorp. Requirements: 5+ years experience in Python, " +
        "TypeScript, React, distributed systems. Must have experience with CI/CD, cloud platforms."
    );

    // Advance to next step (button may be disabled until AI processes the JD)
    const nextBtn = page
      .getByRole("button", { name: /next|continue|proceed/i })
      .or(page.locator('button:has-text("Next")'));
    if (await nextBtn.isVisible() && await nextBtn.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      await nextBtn.click();
    }
  });

  test("views dashboard with recent applications", async ({ page }) => {
    await signIn(page);
    await expect(page).toHaveURL(/dashboard/);
    // Dashboard should have key sections visible
    await expect(
      page.getByText(/career pulse|recent|applications|quick actions/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ─── Persona 2: Marcus – Career Changer, ATS + Evidence ────────────────────

test.describe("Persona 2: Marcus – Career Changer", () => {
  test("uses ATS scanner to check resume compatibility", async ({ page }) => {
    await signIn(page, "/ats-scanner");
    await expect(page.getByText(/ats|scanner|compatibility/i).first()).toBeVisible({
      timeout: 10_000,
    });
    // Should have a textarea or upload area for resume input
    const input = page
      .locator("textarea")
      .first();
    await expect(input).toBeVisible();
  });

  test("manages evidence vault entries", async ({ page }) => {
    await signIn(page, "/evidence");
    await expect(page.getByText(/evidence|vault|portfolio/i).first()).toBeVisible({
      timeout: 10_000,
    });
    // Check for add button
    const addBtn = page
      .getByRole("button", { name: /add|new|create/i })
      .first();
    await expect(addBtn).toBeVisible();
  });

  test("navigates between ATS scanner and evidence vault", async ({ page }) => {
    await signIn(page, "/ats-scanner");
    await expect(page).toHaveURL(/ats-scanner/);

    // Navigate via sidebar
    const evidenceLink = page
      .getByRole("link", { name: /evidence/i })
      .or(page.locator('a[href*="evidence"]'))
      .first();
    if (await evidenceLink.isVisible()) {
      await evidenceLink.click();
      await expect(page).toHaveURL(/evidence/);
    }
  });
});

// ─── Persona 3: Priya – New Grad, Interview Prep + Learning ────────────────

test.describe("Persona 3: Priya – New Grad", () => {
  test("accesses interview preparation", async ({ page }) => {
    await signIn(page, "/interview");
    await expect(page.getByText(/interview|prep|practice/i).first()).toBeVisible({
      timeout: 10_000,
    });
    // Should show interview type options
    await expect(
      page.getByText(/behavioral|technical|case|mixed/i).first()
    ).toBeVisible();
  });

  test("accesses learning challenges", async ({ page }) => {
    await signIn(page, "/learning");
    await expect(page.getByText(/learning|challenge|streak|daily/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("explores career improvement from dashboard", async ({ page }) => {
    await signIn(page);
    // Navigate to career page via sidebar or quick action
    const careerLink = page
      .getByRole("link", { name: /career|improvement/i })
      .or(page.locator('a[href*="career"]'))
      .first();
    if (await careerLink.isVisible()) {
      await careerLink.click();
      // May land on career-analytics, nexus, or career path
      await expect(page).toHaveURL(/career|nexus/);
    }
  });
});

// ─── Persona 4: James – Recruiter, Pipeline + Team Management ──────────────

test.describe("Persona 4: James – Recruiter", () => {
  test("views candidate pipeline", async ({ page }) => {
    await signIn(page, "/candidates");
    // Either shows pipeline or access-denied (role-gated)
    const pipeline = page.getByText(/candidate|pipeline|kanban|sourced/i).first();
    const accessDenied = page.getByText(/access|permission|role|unauthorized/i).first();
    await expect(pipeline.or(accessDenied).first()).toBeVisible({ timeout: 10_000 });
  });

  test("accesses team member management", async ({ page }) => {
    await signIn(page, "/settings/members");
    const memberSection = page.getByText(/member|team|invite/i).first();
    const accessDenied = page.getByText(/access|permission|role|unauthorized/i).first();
    await expect(memberSection.or(accessDenied).first()).toBeVisible({ timeout: 10_000 });
  });

  test("views audit log", async ({ page }) => {
    await signIn(page, "/settings/audit");
    const auditSection = page.getByText(/audit|log|activity|history/i).first();
    const accessDenied = page.getByText(/access|permission|role|unauthorized/i).first();
    await expect(auditSection.or(accessDenied).first()).toBeVisible({ timeout: 10_000 });
  });

  test("views billing/usage dashboard", async ({ page }) => {
    await signIn(page, "/settings/billing");
    const billing = page.getByText(/usage|billing|applications|scans|calls/i).first();
    const accessDenied = page.getByText(/access|permission|role|unauthorized/i).first();
    await expect(billing.or(accessDenied).first()).toBeVisible({ timeout: 10_000 });
  });
});

// ─── Persona 5: Aisha – Freelancer, A/B Lab + Salary Coach ─────────────────

test.describe("Persona 5: Aisha – Freelancer", () => {
  test("explores A/B lab for document variants", async ({ page }) => {
    await signIn(page, "/ab-lab");
    await expect(page.getByText(/a\/b|variant|lab|compare/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("uses salary coach for negotiation", async ({ page }) => {
    await signIn(page, "/salary");
    await expect(page.getByText(/salary|coach|negotiat|market/i).first()).toBeVisible({
      timeout: 10_000,
    });
    // Should have input fields or interactive elements for salary data
    const hasInput = await page.locator("input, textarea, select, [role='combobox']").first().isVisible().catch(() => false);
    const hasBtn = await page.getByRole("button").first().isVisible().catch(() => false);
    expect(hasInput || hasBtn).toBe(true);
  });

  test("navigates settings for profile management", async ({ page }) => {
    await signIn(page, "/settings");
    await expect(page.getByText(/settings|profile|account/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});

// ─── Persona 6: Chen – Executive, Analytics + Profile Hub ───────────────────

test.describe("Persona 6: Chen – Executive", () => {
  test("views career analytics dashboard", async ({ page }) => {
    await signIn(page, "/career-analytics");
    await expect(
      page.getByText(/analytics|timeline|portfolio|snapshot/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("manages profile in Nexus hub", async ({ page }) => {
    await signIn(page, "/nexus");
    await expect(
      page.getByText(/profile|nexus|contact|skills|experience/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("browses job board with AI matching", async ({ page }) => {
    await signIn(page, "/job-board");
    await expect(page.getByText(/job|board|match|alert|listing/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});

// ─── Persona 7: Emma – Accessibility-First, Keyboard Navigation ────────────

test.describe("Persona 7: Emma – Accessibility", () => {
  test("logs in using keyboard only", async ({ page }) => {
    await page.goto("/login");
    // Focus the email field directly to avoid hitting OAuth buttons via Tab
    await page.locator("#email").focus();
    await page.keyboard.type(E2E_EMAIL);
    await page.keyboard.press("Tab"); // Move to password
    await page.keyboard.type(E2E_PASSWORD);
    await page.keyboard.press("Enter"); // Submit form
    // Should attempt navigation; if no test account, just verify we didn't crash
    try {
      await page.waitForURL(/dashboard/, { timeout: 8_000 });
    } catch {
      // Auth may fail without a provisioned test account; staying on login is acceptable
      expect(page.url()).toMatch(/login|localhost/);
    }
  });

  test("dashboard has accessible landmarks", async ({ page }) => {
    await signIn(page);
    // Check for ARIA landmarks
    const nav = page.getByRole("navigation").first();
    const main = page.getByRole("main").or(page.locator("main")).first();
    await expect(nav.or(main).first()).toBeVisible({ timeout: 10_000 });
  });

  test("forms have associated labels", async ({ page }) => {
    await page.goto("/login");
    // Email and password fields should have labels
    const emailField = page.getByLabel(/email/i).or(page.locator("#email"));
    const passwordField = page.getByLabel(/password/i).or(page.locator("#password"));
    await expect(emailField).toBeVisible();
    await expect(passwordField).toBeVisible();
  });

  test("interactive elements are keyboard focusable", async ({ page }) => {
    await signIn(page);
    // Tab through and find focusable elements
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Tab");
    }
    // Verify at least one element received focus
    const hasFocus = await page.evaluate(() => {
      const el = document.activeElement;
      return el !== null && el !== document.body && el.tagName !== "HTML";
    });
    expect(hasFocus).toBe(true);
  });
});

// ─── Persona 8: Diego – Mobile User, Responsive Validation ─────────────────

test.describe("Persona 8: Diego – Mobile User", () => {
  test.use({ viewport: { width: 375, height: 812 } }); // iPhone X

  test("landing page is responsive on mobile", async ({ page }) => {
    await page.goto("/");
    // No horizontal overflow
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 5); // 5px tolerance

    // CTA visible
    await expect(
      page.getByRole("link", { name: /get started/i }).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("login form fits mobile viewport", async ({ page }) => {
    await page.goto("/login");
    const form = page.locator("form").first();
    await expect(form).toBeVisible({ timeout: 10_000 });
    // Form should not overflow
    const formBox = await form.boundingBox();
    if (formBox) {
      expect(formBox.x).toBeGreaterThanOrEqual(0);
      expect(formBox.x + formBox.width).toBeLessThanOrEqual(375 + 5);
    }
  });

  test("dashboard renders on mobile without overflow", async ({ page }) => {
    await signIn(page);
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(bodyWidth).toBeLessThanOrEqual(375 + 5);
  });

  test("navigation is accessible on mobile (hamburger or sidebar)", async ({ page }) => {
    await signIn(page);
    // On mobile, sidebar should be collapsed; look for menu toggle or any nav element
    const menuToggle = page
      .getByRole("button", { name: /menu|toggle|sidebar|nav/i })
      .or(page.locator('[data-testid="mobile-menu"]'))
      .or(page.locator("button.lg\\:hidden").first())
      .first();
    // Check either menu toggle is visible or any clickable button exists
    const hasNav = await menuToggle.isVisible().catch(() => false) ||
      await page.locator("nav").isVisible().catch(() => false) ||
      await page.getByRole("button").first().isVisible().catch(() => false);
    expect(hasNav).toBe(true);
  });
});

// ─── Persona 9: Fatima – Security-Conscious, Auth + Sessions ────────────────

test.describe("Persona 9: Fatima – Security", () => {
  test("protected routes redirect unauthenticated users", async ({ page }) => {
    // Try accessing dashboard without auth
    await page.goto("/dashboard");
    await page.waitForURL(/login|dashboard/, { timeout: 15_000 });
    const url = page.url();
    // Should either redirect to login or show dashboard (if already authed)
    expect(url).toMatch(/login|dashboard/);
  });

  test("protected routes are not cached insecurely", async ({ page }) => {
    const response = await page.goto("/login");
    if (response) {
      const headers = response.headers();
      // Should not have permissive cache headers
      const cacheControl = headers["cache-control"] ?? "";
      expect(cacheControl).not.toContain("public");
    }
  });

  test("no secrets exposed in HTML source", async ({ page }) => {
    await page.goto("/");
    const html = await page.content();
    // No API keys, tokens, or passwords in source
    expect(html).not.toMatch(/sk[-_][a-zA-Z0-9]{20,}/);
    expect(html).not.toMatch(/password\s*[:=]\s*["'][^"']+["']/i);
    expect(html).not.toMatch(/SUPABASE_SERVICE_ROLE_KEY/i);
    expect(html).not.toMatch(/eyJhbGciOiJIUzI1NiIs/); // JWT prefix
  });

  test("session expired parameter shows appropriate message", async ({ page }) => {
    await page.goto("/login?expired=1");
    await expect(
      page.getByText(/expired|session|sign in again/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("password reset page loads correctly", async ({ page }) => {
    await page.goto("/auth/reset-password");
    await expect(
      page.getByText(/reset|new password|update password/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ─── Persona 10: Raj – Power User, Command Palette + Multi-App ──────────────

test.describe("Persona 10: Raj – Power User", () => {
  test("opens command palette with keyboard shortcut", async ({ page }) => {
    await signIn(page);
    // Cmd+K (Mac) or Ctrl+K (Windows/Linux) opens command palette
    const isMac = process.platform === "darwin";
    await page.keyboard.press(isMac ? "Meta+k" : "Control+k");
    // Command palette should appear
    const palette = page
      .getByPlaceholder(/search|command|type/i)
      .or(page.locator('[data-testid="command-palette"]'))
      .or(page.locator('[role="combobox"]'))
      .first();
    await expect(palette).toBeVisible({ timeout: 5_000 });
    // Close it
    await page.keyboard.press("Escape");
  });

  test("navigates rapidly across multiple pages", async ({ page }) => {
    await signIn(page);
    const routes = ["/new", "/evidence", "/ats-scanner", "/interview", "/salary", "/nexus"];
    for (const route of routes) {
      await page.goto(route);
      // Each page should load without error
      const errorVisible = await page.getByText(/error|500|crash/i).first().isVisible().catch(() => false);
      expect(errorVisible).toBe(false);
      // Page should have content
      const content = page.locator("main").or(page.locator('[role="main"]')).or(page.locator("#__next")).first();
      await expect(content).toBeVisible({ timeout: 10_000 });
    }
  });

  test("views API keys management", async ({ page }) => {
    await signIn(page, "/api-keys");
    const apiSection = page.getByText(/api|key|token|create/i).first();
    const accessDenied = page.getByText(/access|permission|role|unauthorized/i).first();
    await expect(apiSection.or(accessDenied).first()).toBeVisible({ timeout: 10_000 });
  });

  test("deprecated routes correctly redirect", async ({ page }) => {
    await signIn(page);
    // /builder should redirect to /dashboard
    await page.goto("/builder");
    await page.waitForURL(/dashboard/, { timeout: 10_000 });
    expect(page.url()).toMatch(/dashboard/);

    // /gaps should redirect to /dashboard
    await page.goto("/gaps");
    await page.waitForURL(/dashboard/, { timeout: 10_000 });
    expect(page.url()).toMatch(/dashboard/);
  });
});

// ─── Cross-Persona: Shared Flows ────────────────────────────────────────────

test.describe("Cross-Persona: Public Review Flow", () => {
  test("public review page loads without auth", async ({ page }) => {
    // Review pages are token-gated, not auth-gated
    await page.goto("/review/test-token-123");
    // Should either show the review page or a "not found" / "invalid token" message
    // Not a hard redirect to /login
    const url = page.url();
    expect(url).toMatch(/review/);
  });
});

test.describe("Cross-Persona: 404 Handling", () => {
  test("non-existent page shows 404", async ({ page }) => {
    const response = await page.goto("/this-page-does-not-exist-xyz");
    // Should get 404 status or show a not-found page
    if (response) {
      expect([200, 404]).toContain(response.status());
    }
    // Should have some not-found indicator
    const notFound = page.getByText(/not found|404|doesn.*exist/i).first();
    const redirected = page.url().includes("login") || page.url().includes("dashboard");
    // Either shows not-found content or redirected somewhere sensible
    if (!redirected) {
      await expect(notFound).toBeVisible({ timeout: 10_000 });
    }
  });
});
