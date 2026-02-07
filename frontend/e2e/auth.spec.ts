import { test, expect } from "@playwright/test";

/**
 * E2E Tests for Authentication Flow
 * Tests login, registration, and auth-protected routes
 */

test.describe("Authentication", () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing auth state
    await page.context().clearCookies();
  });

  test("login page loads correctly", async ({ page }) => {
    await page.goto("/login");

    // Check page elements
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
    await expect(page.getByPlaceholder(/email/i)).toBeVisible();
    await expect(page.getByPlaceholder(/password/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("shows validation errors for empty form", async ({ page }) => {
    await page.goto("/login");

    // Click sign in without filling form
    await page.getByRole("button", { name: /sign in/i }).click();

    // Should show validation feedback or stay on page
    await expect(page).toHaveURL(/login/);
  });

  test("register mode shows name field", async ({ page }) => {
    await page.goto("/login?mode=register");

    // Registration mode should show additional fields
    await expect(page.getByRole("heading", { name: /create account/i })).toBeVisible();
    await expect(page.getByPlaceholder(/full name/i)).toBeVisible();
  });

  test("can switch between login and register modes", async ({ page }) => {
    await page.goto("/login");

    // Should start in login mode
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

    // Click to switch to register
    await page.getByText(/create an account/i).click();
    await expect(page).toHaveURL(/mode=register/);
    await expect(page.getByRole("heading", { name: /create account/i })).toBeVisible();

    // Switch back to login
    await page.getByText(/already have an account/i).click();
    await expect(page).not.toHaveURL(/mode=register/);
  });

  test("unauthenticated user redirects to login from dashboard", async ({ page }) => {
    // Try to access protected route
    await page.goto("/dashboard");

    // Should redirect to login
    await expect(page).toHaveURL(/login/);
  });

  test("forgot password link exists", async ({ page }) => {
    await page.goto("/login");

    // Check forgot password functionality exists
    await expect(page.getByText(/forgot.*password/i)).toBeVisible();
  });

  test("Google sign in button exists", async ({ page }) => {
    await page.goto("/login");

    // Check for Google OAuth button
    await expect(page.getByRole("button", { name: /google/i })).toBeVisible();
  });
});

test.describe("Protected Routes", () => {
  // These tests verify that unauthenticated users can't access protected content
  const protectedRoutes = [
    "/dashboard",
    "/new",
    "/evidence",
    "/career",
    "/applications/test-id",
  ];

  for (const route of protectedRoutes) {
    test(`${route} redirects unauthenticated users to login`, async ({ page }) => {
      await page.context().clearCookies();
      await page.goto(route);
      await expect(page).toHaveURL(/login/);
    });
  }
});
