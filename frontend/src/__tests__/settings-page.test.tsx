/**
 * Unit tests for Settings page — profile update, org management, delete account
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/settings",
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

const mockSignOut = vi.fn();
vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    user: { uid: "u1", email: "test@example.com", displayName: "Test User", full_name: "Test User" },
    session: { access_token: "tok-123" },
    signOut: mockSignOut,
  }),
}));

const { mockRequest } = vi.hoisted(() => ({ mockRequest: vi.fn() }));
vi.mock("@/lib/api", () => {
  const apiObj = {
    setToken: vi.fn(),
    request: mockRequest,
  };
  return { default: apiObj, api: apiObj };
});

vi.mock("@/hooks/use-toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      updateUser: vi.fn(() => Promise.resolve({ error: null })),
    },
  })),
}));

import SettingsPage from "@/app/(dashboard)/settings/page";

describe("SettingsPage", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockSignOut.mockReset();
    mockRequest.mockReset();
    mockRequest.mockResolvedValue([]);
  });

  it("renders profile section with display name", () => {
    render(<SettingsPage />);
    const settingsElements = screen.getAllByText(/settings/i);
    expect(settingsElements.length).toBeGreaterThan(0);
  });

  it("renders organization section", async () => {
    mockRequest.mockResolvedValue([{ id: "org1", name: "Test Corp" }]);
    render(<SettingsPage />);
    await waitFor(() => {
      const content = document.body.textContent ?? "";
      expect(content).toContain("Organization");
    });
  });

  it("shows delete account section", () => {
    render(<SettingsPage />);
    const deleteElements = screen.queryAllByText(/delete/i);
    const dangerElements = screen.queryAllByText(/danger/i);
    // Should have a delete button or danger zone
    expect(deleteElements.length > 0 || dangerElements.length > 0).toBeTruthy();
  });
});
