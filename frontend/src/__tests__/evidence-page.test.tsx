/**
 * Unit tests for Evidence page — evidence library, CRUD, file upload
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/evidence",
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

const { mockEvidenceDocs } = vi.hoisted(() => ({
  mockEvidenceDocs: [
    { id: "e1", title: "AWS Certification", type: "Certification", summary: "Passed AWS SAA", tags: ["aws"], relevance: 9, proof_strength: "strong", userId: "u1" },
    { id: "e2", title: "E-commerce Project", type: "Project", summary: "Led redesign", tags: ["react"], relevance: 8, proof_strength: "moderate", userId: "u1" },
  ],
}));

vi.mock("@/lib/firestore", () => ({
  useEvidence: vi.fn(() => ({
    data: mockEvidenceDocs,
    loading: false,
    addItem: vi.fn(),
    removeItem: vi.fn(),
  })),
  computeEvidenceStrengthScore: () => 85,
}));

vi.mock("@/lib/firestore/ops", () => ({
  createEvidence: vi.fn(() => Promise.resolve("e3")),
  deleteEvidence: vi.fn(() => Promise.resolve()),
  uploadEvidenceFile: vi.fn(() => Promise.resolve("https://storage/file.pdf")),
  updateEvidence: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/lib/firestore/storage-utils", () => ({
  resolveFileUrl: vi.fn((url: string) => url),
}));

vi.mock("@/hooks/use-toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/components/ui/confirm-dialog", () => ({
  ConfirmDialog: ({ children }: any) => <>{children}</>,
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

vi.mock("@/lib/api", () => {
  const apiObj = { request: vi.fn(), setToken: vi.fn() };
  return { default: apiObj, api: apiObj };
});

import EvidencePage from "@/app/(dashboard)/evidence/page";

describe("EvidencePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders evidence library heading", async () => {
    render(<EvidencePage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/evidence|library|proof/i);
    });
  });

  it("displays evidence items from Firestore", async () => {
    render(<EvidencePage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toContain("AWS Certification");
    });
  });

  it("shows evidence types", async () => {
    render(<EvidencePage />);
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(text).toMatch(/Certification|Project/);
    });
  });
});
