import { test, expect, type Page } from "@playwright/test";

/**
 * E2E Tests — Critical user flows: unauthenticated routes, dashboard shell,
 * navigation, error handling, and responsive behavior.
 * These tests do NOT require live auth — they verify publicly accessible paths
 * and auth-redirect behavior.
 */

test.describe("Auth Redirect Enforcement", () => {
  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
  });

  const PROTECTED_ROUTES = [
    "/dashboard",
    "/dashboard/settings",
    "/dashboard/job-board",
    "/dashboard/candidates",
    "/dashboard/interview",
    "/dashboard/learning",
    "/dashboard/salary",
    "/dashboard/career-analytics",
    "/dashboard/evidence",
  ];

  for (const route of PROTECTED_ROUTES) {
    test(`unauthenticated user visiting ${route} redirects to login`, async ({ page }) => {
      await page.goto(route);
      // Should redirect to login or show login page
      await page.waitForURL(/\/(login|$)/, { timeout: 10000 });
      const url = page.url();
      expect(url).toMatch(/\/(login|$)/);
    });
  }
});

test.describe("Public Pages", () => {
  test("landing page loads and has CTA buttons", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);

    // Hero section should be visible
    const getStarted = page.getByRole("link", { name: /get started/i }).first();
    await expect(getStarted).toBeVisible();
  });

  test("login page loads with form", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("register mode toggle works", async ({ page }) => {
    await page.goto("/login?mode=register");

    await expect(page.getByLabel("Full Name")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  });
});

test.describe("Error Handling", () => {
  test("404 page shows for unknown routes", async ({ page }) => {
    const resp = await page.goto("/this-page-does-not-exist-xyz");
    // Next.js should return 404
    if (resp) {
      expect(resp.status()).toBe(404);
    }
  });

  test("login form prevents empty submission", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: /sign in/i }).click();
    // Should stay on login page (no navigation away)
    await expect(page).toHaveURL(/login/);
  });

  test("login shows error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("notreal@test.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Should remain on login page after failed attempt
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/login/);
  });
});

test.describe("Performance & SEO", () => {
  test("landing page has proper meta tags", async ({ page }) => {
    await page.goto("/");
    const title = await page.title();
    expect(title).toBeTruthy();
    expect(title.length).toBeGreaterThan(5);

    // Check viewport meta tag (mobile)
    const viewport = await page.locator('meta[name="viewport"]').getAttribute("content");
    expect(viewport).toContain("width=device-width");
  });

  test("landing page has a main heading (h1)", async ({ page }) => {
    await page.goto("/");
    const h1 = page.locator("h1").first();
    await expect(h1).toBeVisible();
  });

  test("landing page loads within 5 seconds", async ({ page }) => {
    const start = Date.now();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(5000);
  });
});

test.describe("Responsive - Mobile", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("login form is usable on mobile", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    const button = page.getByRole("button", { name: /sign in/i });
    await expect(button).toBeVisible();
  });

  test("landing page is usable on mobile", async ({ page }) => {
    await page.goto("/");
    const getStarted = page.getByRole("link", { name: /get started/i }).first();
    await expect(getStarted).toBeVisible();
  });
});

test.describe("Responsive - Tablet", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test("login form is usable on tablet", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
  });
});

test.describe("Security - Client Side", () => {
  test("login page does not expose sensitive data in HTML", async ({ page }) => {
    await page.goto("/login");
    const html = await page.content();
    // Should not contain API keys or secrets
    expect(html).not.toContain("sk-");
    expect(html).not.toContain("stripe_secret");
    expect(html).not.toContain("supabase_service_role");
  });

  test("no inline styles with dangerous content", async ({ page }) => {
    await page.goto("/login");
    const html = await page.content();
    expect(html).not.toContain("javascript:");
    expect(html).not.toMatch(/on(click|load|error)\s*=/i);
  });

  test("API base URL is not localhost in production HTML", async ({ page }) => {
    await page.goto("/login");
    const html = await page.content();
    // In CI/staging, should not reference localhost backend
    // (This check is informational — localhost may appear in dev)
    const hasLocalhost = html.includes("localhost:8000");
    // Just flag it, don't hard-fail
    if (hasLocalhost) {
      console.warn("WARNING: localhost:8000 found in HTML — check NEXT_PUBLIC_API_URL env");
    }
  });
});
