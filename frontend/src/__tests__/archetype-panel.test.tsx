import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ArchetypePanel } from "@/components/workspace/archetype-panel";
import type { Archetype } from "@/lib/firestore";

afterEach(() => cleanup());

const _arch = (overrides: Partial<Archetype> = {}): Archetype => ({
  name: "Stripe Senior Eng",
  must_have_skills: ["python", "go"],
  nice_to_have_skills: ["rust"],
  years_min: 5,
  years_max: 10,
  salary_band: { p25: 200000, p50: 240000, p75: 280000 },
  cultural_signals: ["ownership", "high agency"],
  ...overrides,
});

describe("ArchetypePanel", () => {
  it("renders nothing when archetypes is undefined", () => {
    const { container } = render(<ArchetypePanel archetypes={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when archetypes is null", () => {
    const { container } = render(<ArchetypePanel archetypes={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for an empty list", () => {
    const { container } = render(<ArchetypePanel archetypes={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders one card per archetype", () => {
    render(
      <ArchetypePanel
        archetypes={[
          _arch({ name: "A" }),
          _arch({ name: "B" }),
          _arch({ name: "C" }),
        ]}
      />
    );
    expect(screen.getAllByTestId("atlas-archetype-card")).toHaveLength(3);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
  });

  it("renders the years-range badge when present", () => {
    render(<ArchetypePanel archetypes={[_arch({ years_min: 3, years_max: 7 })]} />);
    expect(screen.getByText("3–7y")).toBeInTheDocument();
  });

  it("formats salary band with k-suffix", () => {
    render(
      <ArchetypePanel
        archetypes={[
          _arch({ salary_band: { p25: 180000, p50: 220000, p75: 260000 } }),
        ]}
      />
    );
    const sal = screen.getByTestId("atlas-archetype-salary");
    expect(sal.textContent).toMatch(/p25.*\$180k/);
    expect(sal.textContent).toMatch(/p50.*\$220k/);
    expect(sal.textContent).toMatch(/p75.*\$260k/);
  });

  it("hides the salary row when salary_band is empty", () => {
    render(<ArchetypePanel archetypes={[_arch({ salary_band: {} })]} />);
    expect(screen.queryByTestId("atlas-archetype-salary")).toBeNull();
  });

  it("renders must-have and nice-to-have skills as chips", () => {
    render(
      <ArchetypePanel
        archetypes={[
          _arch({
            must_have_skills: ["python", "kafka"],
            nice_to_have_skills: ["rust", "scala"],
          }),
        ]}
      />
    );
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByText("kafka")).toBeInTheDocument();
    expect(screen.getByText("rust")).toBeInTheDocument();
    expect(screen.getByText("scala")).toBeInTheDocument();
  });

  it("renders cultural signals joined by middots", () => {
    render(
      <ArchetypePanel
        archetypes={[
          _arch({ cultural_signals: ["ownership", "writing-first", "async"] }),
        ]}
      />
    );
    expect(screen.getByText(/ownership · writing-first · async/)).toBeInTheDocument();
  });

  it("emits the panel header with generated count", () => {
    render(<ArchetypePanel archetypes={[_arch(), _arch({ name: "X" })]} />);
    expect(screen.getByText("Target archetypes")).toBeInTheDocument();
    expect(screen.getByText("(2 generated)")).toBeInTheDocument();
  });

  it("defensive: ignores non-array fields gracefully", () => {
    render(
      <ArchetypePanel
        archetypes={[
          {
            name: "Defensive",
            // intentionally malformed shapes — TS-cast for the test
            must_have_skills: undefined as unknown as string[],
            nice_to_have_skills: undefined as unknown as string[],
            years_min: undefined as unknown as number,
            years_max: undefined as unknown as number,
            salary_band: {},
            cultural_signals: undefined as unknown as string[],
          },
        ]}
      />
    );
    // The card still renders — just no chips/badges
    expect(screen.getByTestId("atlas-archetype-card")).toBeInTheDocument();
    expect(screen.getByText("Defensive")).toBeInTheDocument();
  });

  it("renders the rationale row when present", () => {
    render(
      <ArchetypePanel
        archetypes={[_arch({ rationale: "Mid-stage fintech, scale focus." })]}
      />
    );
    expect(screen.getByTestId("atlas-archetype-rationale").textContent).toBe(
      "Mid-stage fintech, scale focus."
    );
  });

  it("hides the years badge when both bounds are zero", () => {
    const { container } = render(
      <ArchetypePanel
        archetypes={[_arch({ years_min: 0, years_max: 0 })]}
      />
    );
    expect(container.textContent).not.toContain("0–0y");
  });
});
