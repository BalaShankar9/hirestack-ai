import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CoachPanel, type CoachAction } from "@/components/workspace/coach-panel";

afterEach(() => {
  cleanup();
});

describe("CoachPanel", () => {
  it("renders panel title and default description", () => {
    render(<CoachPanel actions={[]} />);

    expect(screen.getByText("Coach panel")).toBeInTheDocument();
    expect(screen.getByText("Explainable, action-based guidance.")).toBeInTheDocument();
  });

  it("renders custom status line", () => {
    render(<CoachPanel actions={[]} statusLine="3 open tasks · 5 evidence" />);

    expect(screen.getByText("3 open tasks · 5 evidence")).toBeInTheDocument();
  });

  it("shows empty state when no actions provided", () => {
    const { container } = render(<CoachPanel actions={[]} />);

    expect(screen.getByText("No actions right now.")).toBeInTheDocument();
    expect(container.textContent).toContain("When gaps or tasks appear");
  });

  it("renders fix action with correct styling", () => {
    const actions: CoachAction[] = [
      {
        kind: "fix",
        title: 'Add "React" to a top bullet (with proof)',
        why: "Missing keywords reduce ATS match.",
        cta: "Open CV editor",
        onClick: vi.fn(),
      },
    ];

    render(<CoachPanel actions={actions} />);

    expect(screen.getByText('Add "React" to a top bullet (with proof)')).toBeInTheDocument();
    expect(screen.getByText("Missing keywords reduce ATS match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open CV editor/i })).toBeInTheDocument();
  });

  it("renders collect action with correct styling", () => {
    const actions: CoachAction[] = [
      {
        kind: "collect",
        title: "Add 2 evidence items",
        why: "Evidence makes your keywords credible.",
        cta: "Open Evidence Vault",
        onClick: vi.fn(),
      },
    ];

    render(<CoachPanel actions={actions} />);

    expect(screen.getByText("Add 2 evidence items")).toBeInTheDocument();
    expect(screen.getByText("Evidence makes your keywords credible.")).toBeInTheDocument();
  });

  it("renders write action with correct styling", () => {
    const actions: CoachAction[] = [
      {
        kind: "write",
        title: "Snapshot this version",
        why: "Versioning lets you iterate safely.",
        cta: "Save snapshot",
        onClick: vi.fn(),
      },
    ];

    render(<CoachPanel actions={actions} />);

    expect(screen.getByText("Snapshot this version")).toBeInTheDocument();
    expect(screen.getByText("Versioning lets you iterate safely.")).toBeInTheDocument();
  });

  it("renders review action with correct styling", () => {
    const actions: CoachAction[] = [
      {
        kind: "review",
        title: "Lock your confirmed facts",
        why: "We only optimize what you can stand behind.",
        cta: "Lock facts",
        onClick: vi.fn(),
      },
    ];

    render(<CoachPanel actions={actions} />);

    expect(screen.getByText("Lock your confirmed facts")).toBeInTheDocument();
  });

  it("calls onClick when action button is clicked", () => {
    const onClick = vi.fn();
    const actions: CoachAction[] = [
      {
        kind: "fix",
        title: "Fix missing keyword",
        why: "Improves ATS match.",
        cta: "Fix now",
        onClick,
      },
    ];

    render(<CoachPanel actions={actions} />);

    fireEvent.click(screen.getByRole("button", { name: /Fix now/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disables button when onClick is not provided", () => {
    const actions: CoachAction[] = [
      {
        kind: "fix",
        title: "Fix missing keyword",
        why: "Improves ATS match.",
        cta: "Fix now",
      },
    ];

    render(<CoachPanel actions={actions} />);

    const button = screen.getByRole("button", { name: /Fix now/i });
    expect(button).toBeDisabled();
  });

  it("only shows first 3 actions when more are provided", () => {
    const actions: CoachAction[] = [
      { kind: "fix", title: "Action 1", why: "Why 1", cta: "CTA 1", onClick: vi.fn() },
      { kind: "write", title: "Action 2", why: "Why 2", cta: "CTA 2", onClick: vi.fn() },
      { kind: "collect", title: "Action 3", why: "Why 3", cta: "CTA 3", onClick: vi.fn() },
      { kind: "review", title: "Action 4", why: "Why 4", cta: "CTA 4", onClick: vi.fn() },
    ];

    render(<CoachPanel actions={actions} />);

    expect(screen.getByText("Action 1")).toBeInTheDocument();
    expect(screen.getByText("Action 2")).toBeInTheDocument();
    expect(screen.getByText("Action 3")).toBeInTheDocument();
    expect(screen.queryByText("Action 4")).not.toBeInTheDocument();
  });

  it("renders coach principle section", () => {
    const { container } = render(<CoachPanel actions={[]} />);

    expect(screen.getByText("Coach principle")).toBeInTheDocument();
    expect(container.textContent).toContain("spray keywords");
  });
});
