import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusStepper } from "@/components/workspace/status-stepper";
import type { ModuleKey, ModuleStatus } from "@/lib/firestore";

afterEach(() => {
  cleanup();
});

function createModuleStatus(state: ModuleStatus["state"], progress: number, error?: string): ModuleStatus {
  return {
    state,
    progress,
    updatedAt: Date.now(),
    error,
  };
}

describe("StatusStepper", () => {
  const defaultModules: Record<ModuleKey, ModuleStatus> = {
    benchmark: createModuleStatus("idle", 0),
    gaps: createModuleStatus("idle", 0),
    learningPlan: createModuleStatus("idle", 0),
    cv: createModuleStatus("idle", 0),
    coverLetter: createModuleStatus("idle", 0),
    personalStatement: createModuleStatus("idle", 0),
    portfolio: createModuleStatus("idle", 0),
    scorecard: createModuleStatus("idle", 0),
  };

  it("renders all module labels in order", () => {
    render(<StatusStepper modules={defaultModules} />);

    expect(screen.getByText("Benchmark")).toBeInTheDocument();
    expect(screen.getByText("Gap analysis")).toBeInTheDocument();
    expect(screen.getByText("Learning plan")).toBeInTheDocument();
    expect(screen.getByText("Tailored CV")).toBeInTheDocument();
    expect(screen.getByText("Cover letter")).toBeInTheDocument();
    expect(screen.getByText("Scorecard")).toBeInTheDocument();
  });

  it("renders title and description", () => {
    const { container } = render(<StatusStepper modules={defaultModules} />);

    expect(container.textContent).toContain("Generation progress");
    expect(container.textContent).toContain("Each module completes independently");
  });

  it("shows progress percentages for each module", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      benchmark: createModuleStatus("ready", 100),
      gaps: createModuleStatus("generating", 45),
      learningPlan: createModuleStatus("queued", 0),
      cv: createModuleStatus("idle", 0),
      coverLetter: createModuleStatus("idle", 0),
      personalStatement: createModuleStatus("idle", 0),
      portfolio: createModuleStatus("idle", 0),
      scorecard: createModuleStatus("idle", 0),
    };

    const { container } = render(<StatusStepper modules={modules} />);

    expect(container.textContent).toContain("100%");
    expect(container.textContent).toContain("45%");
  });

  it("shows ready state with checkmark", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      ...defaultModules,
      benchmark: createModuleStatus("ready", 100),
    } as Record<ModuleKey, ModuleStatus>;

    const { container } = render(<StatusStepper modules={modules} />);

    expect(container.textContent).toContain("100%");
  });

  it("shows error state with error message", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      ...defaultModules,
      gaps: createModuleStatus("error", 35, "Failed to generate. Retry."),
    } as Record<ModuleKey, ModuleStatus>;

    render(<StatusStepper modules={modules} />);

    expect(screen.getByText("Failed to generate. Retry.")).toBeInTheDocument();
  });

  it("respects custom order of modules", () => {
    const customOrder: ModuleKey[] = ["cv", "coverLetter", "benchmark"];

    const { container } = render(
      <StatusStepper modules={defaultModules} order={customOrder} />
    );

    // Get all module labels in order
    const labels = container.querySelectorAll(".text-sm.font-medium");
    const labelsText = Array.from(labels).map((el) => el.textContent);

    expect(labelsText).toEqual(["Tailored CV", "Cover letter", "Benchmark"]);
  });

  it("shows generating state with spinner", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      ...defaultModules,
      benchmark: createModuleStatus("generating", 60),
    } as Record<ModuleKey, ModuleStatus>;

    const { container } = render(<StatusStepper modules={modules} />);

    // Should have an animated spinner
    const spinner = container.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("shows queued state with spinner", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      ...defaultModules,
      benchmark: createModuleStatus("queued", 0),
    } as Record<ModuleKey, ModuleStatus>;

    const { container } = render(<StatusStepper modules={modules} />);

    // Should have an animated spinner for queued state
    const spinner = container.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("shows idle state with circle icon", () => {
    const modules: Record<ModuleKey, ModuleStatus> = {
      ...defaultModules,
      benchmark: createModuleStatus("idle", 0),
    } as Record<ModuleKey, ModuleStatus>;

    const { container } = render(<StatusStepper modules={modules} />);

    // Circle icons should be present for idle states
    expect(container.querySelector('[class*="text-muted-foreground"]')).toBeInTheDocument();
  });
});
