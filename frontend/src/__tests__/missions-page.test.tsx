import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listMock = vi.fn();
const updateMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
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
      list: (...args: any[]) => listMock(...args),
      update: (...args: any[]) => updateMock(...args),
    },
  };
  return { default: api, api };
});

import MissionsPage from "@/app/(dashboard)/missions/page";

describe("MissionsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    updateMock.mockReset();
  });

  it("renders mission cards from the API", async () => {
    listMock.mockResolvedValue({
      items: [
        {
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
        },
      ],
      count: 1,
    });

    render(<MissionsPage />);

    await waitFor(() => expect(screen.getByText("Design Leadership")).toBeInTheDocument());
    expect(screen.getByText(/4.4\/5 fit floor/i)).toBeInTheDocument();
    expect(screen.getByText(/open inbox/i)).toBeInTheDocument();
  });

  it("lets the user pause an active mission", async () => {
    listMock.mockResolvedValue({
      items: [
        {
          id: "mission-1",
          user_id: "user-1",
          name: "Design Leadership",
          status: "active",
          role_titles: ["Staff Product Designer"],
          locations: ["Remote"],
          comp_band_min: 180000,
          comp_band_max: 230000,
          must_haves: [],
          deal_breakers: [],
          min_fit_score: 4.4,
          target_volume_per_week: 6,
          voice_preset: "confident_selective",
          created_at: "2026-05-09T00:00:00+00:00",
          paused_at: null,
        },
      ],
      count: 1,
    });
    updateMock.mockResolvedValue({
      id: "mission-1",
      user_id: "user-1",
      name: "Design Leadership",
      status: "paused",
      role_titles: ["Staff Product Designer"],
      locations: ["Remote"],
      comp_band_min: 180000,
      comp_band_max: 230000,
      must_haves: [],
      deal_breakers: [],
      min_fit_score: 4.4,
      target_volume_per_week: 6,
      voice_preset: "confident_selective",
      created_at: "2026-05-09T00:00:00+00:00",
      paused_at: "2026-05-09T01:00:00+00:00",
    });

    render(<MissionsPage />);

    await waitFor(() => expect(screen.getByText("Design Leadership")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: /^pause$/i })[0]);

    await waitFor(() => expect(updateMock).toHaveBeenCalledWith("mission-1", { status: "paused" }));
    expect(screen.getByText("paused")).toBeInTheDocument();
  });
});