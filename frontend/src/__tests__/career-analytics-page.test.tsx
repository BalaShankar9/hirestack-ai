/**
 * Unit tests for Career Analytics page — timeline, portfolio, snapshots
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/career-analytics",
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    user: { uid: "u1", email: "test@example.com" },
    session: { access_token: "tok-123" },
  }),
}));

const { mockTimeline } = vi.hoisted(() => ({
  mockTimeline: [
    { id: "t1", captured_at: "2025-01-01", overall_score: 72 },
    { id: "t2", captured_at: "2025-02-01", overall_score: 78 },
    { id: "t3", captured_at: "2025-03-01", overall_score: 85 },
  ],
}));

vi.mock("@/lib/api", () => {
  const apiObj = {
    request: vi.fn(),
    setToken: vi.fn(),
    career: {
      timeline: vi.fn(() => Promise.resolve(mockTimeline)),
      portfolio: vi.fn(() => Promise.resolve({ total_applications: 5, total_skills: 12 })),
      snapshot: vi.fn(() => Promise.resolve({ id: "snap1", overall_score: 88 })),
    },
  };
  return { default: apiObj, api: apiObj };
});

vi.mock("@/hooks/use-toast", () => ({
  toast: vi.fn(),
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    h1: ({ children, ...props }: any) => <h1 {...props}>{children}</h1>,
    h2: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
    section: ({ children, ...props }: any) => <section {...props}>{children}</section>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import CareerAnalyticsPage from "@/app/(dashboard)/career-analytics/page";

describe("CareerAnalyticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders career analytics heading", async () => {
    render(<CareerAnalyticsPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/progress|career|analytics/i);
    });
  });

  it("fetches timeline data on mount", async () => {
    const { api } = await import("@/lib/api");
    render(<CareerAnalyticsPage />);
    await waitFor(() => {
      expect(api.career.timeline).toHaveBeenCalled();
    });
  });

  it("fetches portfolio summary on mount", async () => {
    const { api } = await import("@/lib/api");
    render(<CareerAnalyticsPage />);
    await waitFor(() => {
      expect(api.career.portfolio).toHaveBeenCalled();
    });
  });

  it("shows capture snapshot button", async () => {
    render(<CareerAnalyticsPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/snapshot|capture/i);
    });
  });
});
