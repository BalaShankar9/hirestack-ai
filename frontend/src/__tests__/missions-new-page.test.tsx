import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const createMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
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
      create: (...args: any[]) => createMock(...args),
    },
  };
  return { default: api, api };
});

import MissionSetupPage from "@/app/(dashboard)/missions/new/page";

describe("MissionSetupPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    createMock.mockReset();
  });

  it("walks through the wizard and creates a mission", async () => {
    createMock.mockResolvedValue({ id: "mission-1" });

    render(<MissionSetupPage />);

    fireEvent.change(screen.getByLabelText(/mission name/i), {
      target: { value: "Design Leadership" },
    });
    fireEvent.change(screen.getByLabelText(/target roles/i), {
      target: { value: "Staff Product Designer\nDesign Director" },
    });

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /create mission/i }));

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Design Leadership",
          role_titles: ["Staff Product Designer", "Design Director"],
          voice_preset: "confident_selective",
        }),
      ),
    );
    expect(pushMock).toHaveBeenCalledWith("/missions/mission-1");
  });
});