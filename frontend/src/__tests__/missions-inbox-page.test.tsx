import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMissionMock = vi.fn();
const listDraftsMock = vi.fn();
const syncMissionMock = vi.fn();
const updateDraftMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "mission-1" }),
}));

vi.mock("@/components/providers", () => ({
  useAuth: () => ({
    session: { access_token: "tok" },
  }),
}));

vi.mock("@/lib/api", () => {
  const api = {
    setToken: vi.fn(),
    missions: {
      get: (...args: any[]) => getMissionMock(...args),
      listDrafts: (...args: any[]) => listDraftsMock(...args),
      sync: (...args: any[]) => syncMissionMock(...args),
      updateDraft: (...args: any[]) => updateDraftMock(...args),
    },
  };
  return { default: api, api };
});

import MissionInboxPage from "@/app/(dashboard)/missions/[id]/page";

describe("MissionInboxPage", () => {
  beforeEach(() => {
    getMissionMock.mockReset();
    listDraftsMock.mockReset();
    syncMissionMock.mockReset();
    updateDraftMock.mockReset();

    syncMissionMock.mockResolvedValue({
      status: "ok",
      mission_id: "mission-1",
      scanned_applications: 7,
      matched_applications: 2,
      created: 1,
      updated: 1,
      count: 2,
    });
    getMissionMock.mockResolvedValue({
      id: "mission-1",
      user_id: "user-1",
      name: "Design Leadership",
      status: "active",
      role_titles: ["Staff Product Designer"],
      locations: ["Remote"],
      comp_band_min: 180000,
      comp_band_max: 230000,
      must_haves: ["B2B SaaS"],
      deal_breakers: [],
      min_fit_score: 4.4,
      target_volume_per_week: 6,
      voice_preset: "confident_selective",
      created_at: "2026-05-09T00:00:00+00:00",
      paused_at: null,
    });
    listDraftsMock.mockResolvedValue({
      mission_id: "mission-1",
      count: 1,
      items: [
        {
          id: "draft-1",
          mission_id: "mission-1",
          application_id: "application-1",
          surfaced_at: "2026-05-09T02:00:00+00:00",
          prepared_at: "2026-05-09T02:30:00+00:00",
          sent_at: null,
          status: "ready_for_user",
          fit_score: 4.6,
          application: {
            id: "application-1",
            title: "Staff Product Designer",
            role_title: "Staff Product Designer",
            company_name: "Acme",
            status: "draft",
            updated_at: "2026-05-09T02:00:00+00:00",
            fit_score: 4.6,
            source: "tracked_company_auto_prep",
            canonical_url: "https://jobs.example/acme/1",
            company_slug: "acme",
            ready_to_apply: true,
            generated_document_count: 2,
          },
        },
      ],
    });
  });

  it("syncs on load and renders enriched draft metadata", async () => {
    render(<MissionInboxPage />);

    await waitFor(() => expect(syncMissionMock).toHaveBeenCalledWith("mission-1"));
    expect(await screen.findByText("Staff Product Designer")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/ready assets attached/i)).toBeInTheDocument();
    expect(screen.getByText(/last sync scanned 7 applications, matched 2, created 1, and updated 1./i)).toBeInTheDocument();
  });

  it("runs sync again when the user refreshes", async () => {
    render(<MissionInboxPage />);

    await waitFor(() => expect(syncMissionMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getAllByRole("button", { name: /refresh/i })[0]);

    await waitFor(() => expect(syncMissionMock).toHaveBeenCalledTimes(2));
  });
});