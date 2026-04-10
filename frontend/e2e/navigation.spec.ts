import { test, expect, type Page } from "@playwright/test";

/**
 * E2E Tests for Dashboard and Navigation
 * Uses a mock authenticated state for testing protected routes
 */

// Note: For full E2E testing with auth, you would need to either:
// 1. Set up a test Firebase project
// 2. Mock the auth state using page.addInitScript
// 3. Use environment variables for test credentials

test.describe("Landing Page", () => {
  test("home page redirects appropriately", async ({ page }) => {
    await page.goto("/");

    // Should render the marketing landing page for unauthenticated users
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("link", { name: /get started/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
  });

  test("has correct meta tags", async ({ page }) => {
    await page.goto("/login");

    // Check title
    const title = await page.title();
    expect(title).toBeTruthy();
  });
});

test.describe("Navigation Structure", () => {
  test("login page has proper navigation elements", async ({ page }) => {
    await page.goto("/login");

    // Check for branding
    await expect(page.getByRole("link", { name: /hirestack ai/i })).toBeVisible();
  });
});

test.describe("Accessibility", () => {
  test("login page has accessible form elements", async ({ page }) => {
    await page.goto("/login");

    // Check that form inputs have proper labels
    const emailInput = page.getByLabel("Email");
    const passwordInput = page.getByLabel("Password");

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    // Check form is keyboard navigable
    await emailInput.focus();
    await page.keyboard.press("Tab");

    // Next focused element should be password field
    await expect(passwordInput).toBeFocused();
  });

  test("buttons have accessible names", async ({ page }) => {
    await page.goto("/login");

    // All buttons should have accessible names
    const buttons = page.locator("button");
    const count = await buttons.count();

    for (let i = 0; i < count; i++) {
      const button = buttons.nth(i);
      const name = await button.getAttribute("aria-label") || await button.textContent();
      expect(name).toBeTruthy();
    }
  });
});

test.describe("Responsive Design", () => {
  test("login page works on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 }); // iPhone SE
    await page.goto("/login");

    // Form should still be visible
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Sign In$/ })).toBeVisible();
  });

  test("login page works on tablet viewport", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 }); // iPad
    await page.goto("/login");

    // Form should still be visible
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Sign In$/ })).toBeVisible();
  });

  test("login page works on desktop viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/login");

    // Form should still be visible
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Sign In$/ })).toBeVisible();
  });
});

test.describe("Error States", () => {
  test("shows error for invalid credentials", async ({ page }) => {
    await page.goto("/login");

    // Fill in invalid credentials
    await page.getByLabel("Email").fill("invalid@test.com");
    await page.getByLabel("Password").fill("wrongpassword");

    // Submit form
    await page.getByRole("button", { name: /^Sign In$/ }).click();

    // Should show an error message (Supabase will reject)
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10000 });
  });
});

test.describe("Performance", () => {
  test("login page loads within acceptable time", async ({ page }) => {
    const startTime = Date.now();
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const loadTime = Date.now() - startTime;

    // Should load within 5 seconds
    expect(loadTime).toBeLessThan(5000);
  });
});
