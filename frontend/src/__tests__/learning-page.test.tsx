/**
 * Unit tests for Learning page — streak, challenges, progress
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/learning",
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

const { mockProfile } = vi.hoisted(() => ({
  mockProfile: {
    skills: [{ name: "React" }, { name: "TypeScript" }],
    experience: [{ title: "Engineer" }],
  },
}));

vi.mock("@/lib/api", () => {
  const apiObj = {
    request: vi.fn(),
    setToken: vi.fn(),
    profile: {
      get: vi.fn(() => Promise.resolve(mockProfile)),
    },
    learning: {
      getStreak: vi.fn(() => Promise.resolve({ current_streak: 5, best_streak: 10, total_points: 100, accuracy: 85 })),
      getToday: vi.fn(() => Promise.resolve([])),
      generate: vi.fn(() => Promise.resolve([])),
      submitAnswer: vi.fn(() => Promise.resolve({ correct: true, explanation: "Good" })),
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

import LearningPage from "@/app/(dashboard)/learning/page";

describe("LearningPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders learning page heading", async () => {
    render(<LearningPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/learn|challenge|streak/i);
    });
  });

  it("loads profile for personalized challenges", async () => {
    const { api } = await import("@/lib/api");
    render(<LearningPage />);
    await waitFor(() => {
      expect(api.profile.get).toHaveBeenCalled();
    });
  });
});
