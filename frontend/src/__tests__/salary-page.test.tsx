/**
 * Unit tests for Salary Coach page — form, analysis, display
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/salary",
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

vi.mock("@/lib/api", () => {
  const apiObj = {
    request: vi.fn(),
    setToken: vi.fn(),
    profile: {
      get: vi.fn(() => Promise.resolve({
        skills: [{ name: "Python" }],
        experience: [{ title: "Senior Engineer", years: 5 }],
      })),
    },
    salary: {
      analyze: vi.fn(() => Promise.resolve({
        job_title: "Senior Engineer",
        percentile_25: 120000,
        median: 150000,
        percentile_75: 180000,
        recommendation: "You are well positioned",
      })),
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
    p: ({ children, ...props }: any) => <p {...props}>{children}</p>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import SalaryCoachPage from "@/app/(dashboard)/salary/page";

describe("SalaryCoachPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders salary coach heading", async () => {
    render(<SalaryCoachPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/salary|compensation|coach/i);
    });
  });

  it("shows input fields for salary analysis", async () => {
    render(<SalaryCoachPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/job title|title|role/i);
    });
  });

  it("auto-fills from profile", async () => {
    const { api } = await import("@/lib/api");
    render(<SalaryCoachPage />);
    await waitFor(() => {
      expect(api.profile.get).toHaveBeenCalled();
    });
  });
});
