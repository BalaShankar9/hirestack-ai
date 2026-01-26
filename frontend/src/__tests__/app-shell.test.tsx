import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));

vi.mock("firebase/auth", () => ({ signOut: vi.fn() }));
vi.mock("@/lib/firebase", () => ({ auth: {} }));
vi.mock("@/components/providers", () => ({
  useAuth: () => ({ user: { uid: "u1", email: "u1@example.com", displayName: "User" } }),
}));
vi.mock("@/lib/firestore", () => ({
  useApplications: () => ({ data: [], loading: false, error: null }),
}));

describe("AppShell", () => {
  it("renders nav items and opens command palette", () => {
    render(
      <AppShell pageTitle="Dashboard">
        <div>Content</div>
      </AppShell>
    );

    expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    expect(screen.getAllByText("New Application").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence Vault").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Career Lab").length).toBeGreaterThan(0);

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(screen.getByText(/Command palette/i)).toBeInTheDocument();
  });
});
