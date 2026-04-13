/**
 * Unit tests for Candidates page — pipeline, CRUD, search
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/candidates",
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    user: { uid: "u1", email: "test@example.com", displayName: "Test Recruiter" },
    session: { access_token: "tok-123" },
  }),
}));

const { mockRequest } = vi.hoisted(() => ({ mockRequest: vi.fn() }));
vi.mock("@/lib/api", () => {
  const apiObj = {
    request: mockRequest,
    setToken: vi.fn(),
  };
  return { default: apiObj, api: apiObj };
});

vi.mock("@/hooks/use-toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/components/ui/role-gate", () => ({
  RoleGate: ({ children }: any) => <>{children}</>,
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    h1: ({ children, ...props }: any) => <h1 {...props}>{children}</h1>,
    section: ({ children, ...props }: any) => <section {...props}>{children}</section>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import CandidatesPage from "@/app/(dashboard)/candidates/page";

const mockCandidates = [
  { id: "c1", name: "Alice", email: "alice@test.com", pipeline_stage: "sourced", client_company: "Acme" },
  { id: "c2", name: "Bob", email: "bob@test.com", pipeline_stage: "screened", client_company: "Corp" },
];

describe("CandidatesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRequest.mockImplementation((url: string) => {
      if (url.includes("/stats")) return Promise.resolve({ sourced: 1, screened: 1, submitted: 0, interviewing: 0, offered: 0, placed: 0 });
      return Promise.resolve(mockCandidates);
    });
  });

  it("renders candidates page", async () => {
    render(<CandidatesPage />);
    await waitFor(() => {
      expect(document.body.textContent).toContain("Candidate");
    });
  });

  it("loads candidates from API", async () => {
    render(<CandidatesPage />);
    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalled();
    });
  });

  it("shows pipeline stages", async () => {
    render(<CandidatesPage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      // Kanban view should show pipeline stages
      expect(text).toMatch(/sourced|screened|pipeline/i);
    });
  });
});
