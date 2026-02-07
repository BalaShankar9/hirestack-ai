import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModuleCard } from "@/components/workspace/module-card";

type ModuleStatus = {
  state: "idle" | "queued" | "generating" | "ready" | "error";
  progress: number;
  updatedAt: number;
  error?: string;
};

const mockIcon = <span data-testid="mock-icon">📄</span>;

afterEach(() => {
  cleanup();
});

describe("ModuleCard", () => {
  it("renders title, description, and idle state", () => {
    const status: ModuleStatus = {
      state: "idle",
      progress: 0,
      updatedAt: Date.now(),
    };

    render(
      <ModuleCard
        title="Benchmark"
        description="Ideal candidate signal + rubric"
        status={status}
        icon={mockIcon}
      />
    );

    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(screen.getByText("Ideal candidate signal + rubric")).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.getByTestId("mock-icon")).toBeInTheDocument();
  });

  it("renders ready state with checkmark badge", () => {
    const status: ModuleStatus = {
      state: "ready",
      progress: 100,
      updatedAt: Date.now(),
    };

    render(
      <ModuleCard
        title="Gap analysis"
        description="Missing keywords + recommendations"
        status={status}
        icon={mockIcon}
      />
    );

    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("renders generating state with progress bar", () => {
    const status: ModuleStatus = {
      state: "generating",
      progress: 45,
      updatedAt: Date.now(),
    };

    render(
      <ModuleCard
        title="CV"
        description="Building your tailored CV"
        status={status}
        icon={mockIcon}
      />
    );

    expect(screen.getByText("Generating")).toBeInTheDocument();
    expect(screen.getByText("Building module… 45%")).toBeInTheDocument();
  });

  it("renders queued state", () => {
    const status: ModuleStatus = {
      state: "queued",
      progress: 0,
      updatedAt: Date.now(),
    };

    render(
      <ModuleCard
        title="Learning plan"
        description="Sprint-based skill building"
        status={status}
        icon={mockIcon}
      />
    );

    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("renders error state with error message", () => {
    const status: ModuleStatus = {
      state: "error",
      progress: 0,
      updatedAt: Date.now(),
      error: "Failed to generate module. Please retry.",
    };

    render(
      <ModuleCard
        title="Cover letter"
        description="Evidence-first narrative"
        status={status}
        icon={mockIcon}
      />
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Failed to generate module. Please retry.")).toBeInTheDocument();
  });

  it("calls onOpen when Open button is clicked", () => {
    const onOpen = vi.fn();
    const status: ModuleStatus = {
      state: "ready",
      progress: 100,
      updatedAt: Date.now(),
    };

    const { container } = render(
      <ModuleCard
        title="Benchmark"
        description="Ideal candidate signal"
        status={status}
        icon={mockIcon}
        onOpen={onOpen}
      />
    );

    const openButton = container.querySelector('button:not(:disabled)');
    if (openButton) fireEvent.click(openButton);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("calls onRegenerate when Regenerate button is clicked", () => {
    const onRegenerate = vi.fn();
    const status: ModuleStatus = {
      state: "ready",
      progress: 100,
      updatedAt: Date.now(),
    };

    const { container } = render(
      <ModuleCard
        title="Gap analysis"
        description="Missing keywords"
        status={status}
        icon={mockIcon}
        onRegenerate={onRegenerate}
      />
    );

    const buttons = container.querySelectorAll('button');
    const regenerateButton = Array.from(buttons).find(btn => btn.textContent?.includes('Regenerate'));
    if (regenerateButton) fireEvent.click(regenerateButton);
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("disables Open button when onOpen is not provided", () => {
    const status: ModuleStatus = {
      state: "ready",
      progress: 100,
      updatedAt: Date.now(),
    };

    const { container } = render(
      <ModuleCard
        title="Benchmark"
        description="Ideal candidate signal"
        status={status}
        icon={mockIcon}
      />
    );

    const openButton = container.querySelector('button:first-of-type');
    expect(openButton).toHaveAttribute('disabled');
  });
});
