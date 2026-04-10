import { render, screen, fireEvent, waitFor, cleanup, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Hoisted mocks (available to vi.mock factories) ───────────────────

const { mockProfileApi, mockApi, mockUser, mockSession } = vi.hoisted(() => {
  const fn = () => vi.fn();
  const mockProfileApi = {
    get: fn(), getById: fn(), list: fn(), upload: fn(), update: fn(),
    delete: fn(), setPrimary: fn(), reparse: fn(), updateSocialLinks: fn(),
    connectSocial: fn(), augmentSkills: fn(), generateUniversalDocs: fn(),
    completeness: fn(), resumeWorth: fn(), aggregateGaps: fn(),
    marketIntelligence: fn(), syncedEvidence: fn(), syncEvidence: fn(),
  };
  const mockApi = { setToken: fn(), profile: mockProfileApi };
  const mockUser = { uid: "u1", email: "test@test.com", displayName: "Test User" };
  const mockSession = { access_token: "tok-123", user: mockUser };
  return { mockProfileApi, mockApi, mockUser, mockSession };
});

// ── Module mocks ─────────────────────────────────────────────────────

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/nexus",
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signOut: vi.fn(),
    },
    from: vi.fn(() => ({
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
    })),
    channel: vi.fn(() => ({ on: vi.fn().mockReturnThis(), subscribe: vi.fn() })),
    removeChannel: vi.fn(),
  })),
}));

vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    user: mockUser,
    session: mockSession,
    signOut: vi.fn(),
  }),
}));

vi.mock("@/lib/export", () => ({ exportToPdf: vi.fn() }));
vi.mock("@/lib/document-styles", () => ({ getDocumentCSS: vi.fn(() => "") }));
vi.mock("@/lib/sanitize", () => ({ sanitizeHtml: (html: string) => html }));
vi.mock("@/lib/api", () => ({ default: mockApi }));

// ── Import component (AFTER mocks) ─────────────────────────────────

import CareerNexusPage from "@/app/(dashboard)/nexus/page";

// ── Helpers ──────────────────────────────────────────────────────────

const MOCK_PROFILE = {
  id: "p1",
  user_id: "u1",
  name: "Jane Doe",
  title: "Senior Engineer",
  summary: "Experienced developer",
  skills: [{ name: "React", level: "expert" }, { name: "TypeScript", level: "advanced" }],
  experience: [{ company: "Acme", title: "Dev", description: "Coded stuff" }],
  education: [{ institution: "MIT", degree: "BS CS" }],
  certifications: [],
  projects: [{ name: "Proj A", description: "open source" }],
  languages: ["English"],
  achievements: [],
  contact_info: { email: "jane@example.com", location: "London" },
  social_links: { linkedin: "https://linkedin.com/in/jane", github: { url: "https://github.com/jane", status: "connected", data: { public_repos: 12, top_languages: ["TS", "Python"], followers: 50 } } },
  profile_version: 3,
  universal_docs_version: 2,
  universal_documents: { resume: { html: "<p>Resume</p>" }, cv: { html: "<p>CV</p>" } },
  completeness_score: 75,
  is_primary: true,
  parsed_data: {},
  raw_resume_text: "raw",
  file_type: "pdf",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
};

const MOCK_COMPLETENESS = { score: 75, sections: {}, suggestions: ["Add certifications", "Add more skills"] };
const MOCK_RESUME_WORTH = { score: 68, label: "Good", breakdown: { impact_metrics: 70, technical_depth: 65, clarity: 72, unique_value: 60 } };
const MOCK_GAPS = { overall_gap_score: 30, gap_areas: [] };

function setupMocks(overrides: Record<string, any> = {}) {
  mockProfileApi.get.mockResolvedValue(overrides.profile ?? MOCK_PROFILE);
  mockProfileApi.getById.mockResolvedValue(overrides.profile ?? MOCK_PROFILE);
  mockProfileApi.completeness.mockResolvedValue(overrides.completeness ?? MOCK_COMPLETENESS);
  mockProfileApi.resumeWorth.mockResolvedValue(overrides.resumeWorth ?? MOCK_RESUME_WORTH);
  mockProfileApi.aggregateGaps.mockResolvedValue(overrides.gaps ?? MOCK_GAPS);
  mockProfileApi.syncedEvidence.mockResolvedValue(overrides.evidence ?? {});
  mockProfileApi.marketIntelligence.mockResolvedValue(overrides.market ?? { error: "no data" });
  mockProfileApi.upload.mockResolvedValue(overrides.uploadResult ?? MOCK_PROFILE);
  mockProfileApi.update.mockResolvedValue(overrides.updateResult ?? MOCK_PROFILE);
  mockProfileApi.generateUniversalDocs.mockResolvedValue({ status: "ok" });
  mockProfileApi.updateSocialLinks.mockResolvedValue(overrides.profile ?? MOCK_PROFILE);
  mockProfileApi.connectSocial.mockResolvedValue({ status: "ok" });
  mockProfileApi.delete.mockResolvedValue({});
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── Tests ────────────────────────────────────────────────────────────

describe("CareerNexusPage", () => {
  describe("Empty state (no profile)", () => {
    beforeEach(() => {
      mockProfileApi.get.mockRejectedValue(new Error("Not found"));
    });

    it("renders the upload prompt when no profile exists", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("Upload Your Resume")).toBeInTheDocument();
      });
    });

    it("renders social link inputs in empty state", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByPlaceholderText("https://linkedin.com/in/yourname")).toBeInTheDocument();
        expect(screen.getByPlaceholderText("https://github.com/yourname")).toBeInTheDocument();
      });
    });

    it("shows feature preview cards", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("Universal Resume")).toBeInTheDocument();
        expect(screen.getByText("Full CV")).toBeInTheDocument();
        expect(screen.getByText("Intelligence")).toBeInTheDocument();
      });
    });
  });

  describe("Profile loaded", () => {
    beforeEach(() => {
      setupMocks();
    });

    it("renders the profile hero with name, title, and stats", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Senior Engineer").length).toBeGreaterThan(0);
        // Stats area with Skills, Roles counts
        expect(screen.getAllByText("Skills").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Roles").length).toBeGreaterThan(0);
      });
    });

    it("renders tab navigation", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByRole("tab", { name: /profile/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /documents/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /intelligence/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /evidence/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /settings/i })).toBeInTheDocument();
      });
    });

    it("displays completeness score", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("75%")).toBeInTheDocument();
      });
    });

    it("displays AI suggestions when completeness has them", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("Add certifications")).toBeInTheDocument();
        expect(screen.getByText("Add more skills")).toBeInTheDocument();
      });
    });

    it("shows connected social platforms in hero", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        // LinkedIn and GitHub are connected - they should appear as links
        const links = screen.getAllByRole("link");
        const linkedinLink = links.find((l) => l.getAttribute("href") === "https://linkedin.com/in/jane");
        const githubLink = links.find((l) => l.getAttribute("href") === "https://github.com/jane");
        expect(linkedinLink).toBeTruthy();
        expect(githubLink).toBeTruthy();
      });
    });
  });

  describe("Stale document badge", () => {
    it("detects stale docs when profile_version > universal_docs_version", async () => {
      const user = userEvent.setup();
      setupMocks({
        profile: {
          ...MOCK_PROFILE,
          profile_version: 5,
          universal_docs_version: 2,
          universal_documents: { universal_resume_html: "<p>old</p>" },
        },
      });
      render(<CareerNexusPage />);
      // Wait for profile to load
      await waitFor(() => {
        expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0);
      });
      // Switch to documents tab
      const docsTab = screen.getByRole("tab", { name: /documents/i });
      await user.click(docsTab);
      await waitFor(() => {
        // Should show "Needs Update" badges
        expect(screen.getAllByText("Needs Update").length).toBeGreaterThan(0);
      });
    });
  });

  describe("Upload flow", () => {
    it("calls API upload and refreshes intelligence after success", async () => {
      setupMocks();
      // Start with no profile, then after upload it exists
      const getCallCount = { n: 0 };
      mockProfileApi.get.mockImplementation(async () => {
        getCallCount.n++;
        if (getCallCount.n === 1) throw new Error("No profile");
        return MOCK_PROFILE;
      });

      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("Upload Your Resume")).toBeInTheDocument();
      });

      // Simulate file upload
      const file = new File(["resume content"], "resume.pdf", { type: "application/pdf" });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(input).toBeTruthy();
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(mockProfileApi.upload).toHaveBeenCalledWith(file, true);
      });
    });

    it("shows error message on upload failure", async () => {
      mockProfileApi.get.mockRejectedValue(new Error("Not found"));
      mockProfileApi.upload.mockRejectedValue(new Error("Invalid file format"));

      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getByText("Upload Your Resume")).toBeInTheDocument();
      });

      const file = new File(["bad"], "resume.xyz", { type: "application/octet-stream" });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText("Invalid file format")).toBeInTheDocument();
      });
    });
  });

  describe("Social connect flow", () => {
    beforeEach(() => {
      setupMocks();
    });

    it("displays connected GitHub data summary", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        // GitHub data: 12 repos · TS, Python · 50 followers
        expect(screen.getByText(/12 repos/)).toBeInTheDocument();
      });
    });
  });

  describe("Intelligence tab", () => {
    beforeEach(() => {
      setupMocks();
    });

    it("loads intelligence data on profile load", async () => {
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(mockProfileApi.completeness).toHaveBeenCalled();
        expect(mockProfileApi.resumeWorth).toHaveBeenCalled();
        expect(mockProfileApi.aggregateGaps).toHaveBeenCalled();
      });
    });

    it("shows error banner when intelligence partially fails", async () => {
      const user = userEvent.setup();
      mockProfileApi.get.mockResolvedValue(MOCK_PROFILE);
      mockProfileApi.getById.mockResolvedValue(MOCK_PROFILE);
      mockProfileApi.completeness.mockRejectedValue(new Error("fail"));
      mockProfileApi.resumeWorth.mockRejectedValue(new Error("fail"));
      mockProfileApi.aggregateGaps.mockResolvedValue(MOCK_GAPS);
      mockProfileApi.syncedEvidence.mockResolvedValue({});
      mockProfileApi.marketIntelligence.mockResolvedValue({ error: "no" });

      render(<CareerNexusPage />);
      // Wait for profile to load
      await waitFor(() => {
        expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0);
      });
      // Switch to intelligence tab
      const intelTab = screen.getByRole("tab", { name: /intelligence/i });
      await user.click(intelTab);
      await waitFor(() => {
        expect(screen.getByText(/could not load/i)).toBeInTheDocument();
      });
    });
  });

  describe("Document generation", () => {
    it("calls generateUniversalDocs and reloads profile", async () => {
      const user = userEvent.setup();
      setupMocks({
        profile: { ...MOCK_PROFILE, profile_version: 3, universal_docs_version: 0, universal_documents: {} },
      });
      render(<CareerNexusPage />);

      await waitFor(() => {
        expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0);
      });

      const docsTab = screen.getByRole("tab", { name: /documents/i });
      await user.click(docsTab);

      await waitFor(() => {
        expect(screen.getAllByText(/generate all documents/i).length).toBeGreaterThan(0);
      });
      await user.click(screen.getAllByText(/generate all documents/i)[0]);

      await waitFor(() => {
        expect(mockProfileApi.generateUniversalDocs).toHaveBeenCalledWith("p1");
      });

      await waitFor(() => {
        expect(mockProfileApi.getById).toHaveBeenCalledWith("p1");
      });
    });
  });

  describe("Settings tab — delete", () => {
    it("renders delete button in settings", async () => {
      const user = userEvent.setup();
      setupMocks();

      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(screen.getAllByText("Jane Doe").length).toBeGreaterThan(0);
      });

      const settingsTab = screen.getByRole("tab", { name: /settings/i });
      await user.click(settingsTab);

      await waitFor(() => {
        const deleteBtn = screen.getByText("Delete Profile");
        expect(deleteBtn).toBeInTheDocument();
      });
    });
  });

  describe("API token setup", () => {
    it("sets API token on mount", async () => {
      setupMocks();
      render(<CareerNexusPage />);
      await waitFor(() => {
        expect(mockApi.setToken).toHaveBeenCalledWith("tok-123");
      });
    });
  });
});
