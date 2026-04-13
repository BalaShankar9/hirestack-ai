/**
 * Unit tests for Interview page — session setup, question flow, scoring
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/interview",
  useSearchParams: () => new URLSearchParams(),
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

const { mockInterview } = vi.hoisted(() => ({
  mockInterview: {
    start: vi.fn(() => Promise.resolve({ id: "s1", questions: [{ id: "q1", text: "Tell me about yourself" }] })),
    submitAnswer: vi.fn(() => Promise.resolve({ score: 8, feedback: "Good answer" })),
    complete: vi.fn(() => Promise.resolve({ overall_score: 85 })),
    get: vi.fn(() => Promise.resolve(null)),
  },
}));
vi.mock("@/lib/api", () => {
  const apiObj = {
    request: vi.fn(),
    setToken: vi.fn(),
    interview: mockInterview,
    profile: { get: vi.fn(() => Promise.resolve({ title: "Engineer", skills: ["React", "Node"] })) },
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
    h3: ({ children, ...props }: any) => <h3 {...props}>{children}</h3>,
    p: ({ children, ...props }: any) => <p {...props}>{children}</p>,
    section: ({ children, ...props }: any) => <section {...props}>{children}</section>,
    li: ({ children, ...props }: any) => <li {...props}>{children}</li>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import InterviewPage from "@/app/(dashboard)/interview/page";

describe("InterviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders interview setup phase", async () => {
    render(<InterviewPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/interview|mock|practice/i);
    });
  });

  it("shows interview type options", async () => {
    render(<InterviewPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      // Should show at least one interview type
      expect(text).toMatch(/behavioral|technical|situational|case|mixed/i);
    });
  });

  it("shows mode selection options", async () => {
    render(<InterviewPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/practice|timed|live/i);
    });
  });
});
