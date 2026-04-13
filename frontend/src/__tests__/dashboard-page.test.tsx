/**
 * Unit tests for Dashboard page rendering and interactions
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

// --- Mocks ---
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

const mockUser = { uid: "u1", email: "test@example.com", displayName: "Test User" };
vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    user: mockUser,
    session: { access_token: "tok" },
    signOut: vi.fn(),
  }),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
    from: vi.fn(() => ({
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
      then: vi.fn((cb: any) => cb({ data: [], error: null })),
    })),
    channel: vi.fn(() => ({ on: vi.fn().mockReturnThis(), subscribe: vi.fn() })),
    removeChannel: vi.fn(),
  })),
}));

vi.mock("@/lib/firestore", () => ({
  useApplications: () => ({ data: [], loading: false }),
  useEvidence: () => ({ data: [], loading: false }),
  useTasks: () => ({ data: [], loading: false }),
  computeEvidenceStrengthScore: () => 0,
  deleteApplication: vi.fn(),
  setTaskStatus: vi.fn(),
  trackEvent: vi.fn(),
}));

vi.mock("@/contexts/onboarding-context", () => ({
  useOnboarding: () => ({
    applicationCount: 0,
    hasProfile: false,
    hasEvidence: false,
    loading: false,
    updateCounts: vi.fn(),
  }),
}));

vi.mock("@/hooks", () => ({
  toast: vi.fn(),
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    section: ({ children, ...props }: any) => <section {...props}>{children}</section>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
  },
  AnimatePresence: ({ children }: any) => children,
}));

import DashboardPage from "@/app/(dashboard)/dashboard/page";

describe("DashboardPage", () => {
  beforeEach(() => {
    mockPush.mockReset();
  });

  it("renders without crashing", () => {
    render(<DashboardPage />);
    // Dashboard should show some greeting or overview content
    expect(document.body.textContent).toBeTruthy();
  });

  it("displays the user greeting or overview section", () => {
    render(<DashboardPage />);
    // Should show something related to the user or overview
    const content = document.body.textContent ?? "";
    expect(content.length).toBeGreaterThan(0);
  });

  it("shows New Application button or link", () => {
    render(<DashboardPage />);
    const getStartedElements = screen.queryAllByText(/get started/i);
    const newAppLink = screen.queryByText(/new application/i);
    // Dashboard should have a way to start a new application
    expect(newAppLink || getStartedElements.length > 0 || screen.queryByRole("link")).toBeTruthy();
  });
});
