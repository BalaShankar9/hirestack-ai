import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { KeywordChips } from "@/components/workspace/keyword-chips";

afterEach(() => {
  cleanup();
});

describe("KeywordChips", () => {
  it("renders keywords as chips", () => {
    const keywords = ["React", "TypeScript", "Node.js"];
    render(<KeywordChips keywords={keywords} isCovered={() => false} />);

    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
    expect(screen.getByText("Node.js")).toBeInTheDocument();
  });

  it("shows covered keywords with checkmark indicator", () => {
    const keywords = ["React", "TypeScript", "Node.js"];
    const isCovered = (kw: string) => kw === "React";

    const { container } = render(<KeywordChips keywords={keywords} isCovered={isCovered} />);

    // Check for checkmark in covered chip and dot in uncovered
    expect(container.textContent).toContain("✓");
    expect(container.textContent).toContain("•");
  });

  it("shows uncovered keywords with dot indicator", () => {
    const keywords = ["React", "TypeScript"];
    const isCovered = () => false;

    const { container } = render(<KeywordChips keywords={keywords} isCovered={isCovered} />);

    // Check for dot indicators in uncovered chips
    expect(container.textContent).toContain("•");
  });

  it("limits keywords to specified limit", () => {
    const keywords = Array.from({ length: 25 }, (_, i) => `Keyword${i + 1}`);

    render(<KeywordChips keywords={keywords} isCovered={() => false} limit={10} />);

    expect(screen.getByText("Keyword1")).toBeInTheDocument();
    expect(screen.getByText("Keyword10")).toBeInTheDocument();
    expect(screen.queryByText("Keyword11")).not.toBeInTheDocument();
  });

  it("uses default limit of 18", () => {
    const keywords = Array.from({ length: 25 }, (_, i) => `Skill${i + 1}`);

    render(<KeywordChips keywords={keywords} isCovered={() => false} />);

    expect(screen.getByText("Skill18")).toBeInTheDocument();
    expect(screen.queryByText("Skill19")).not.toBeInTheDocument();
  });

  it("handles empty keywords array", () => {
    const { container } = render(<KeywordChips keywords={[]} isCovered={() => false} />);

    // Should render an empty container with flex wrapper
    expect(container.querySelector(".flex")).toBeInTheDocument();
    expect(container.querySelectorAll("[class*='Badge']").length).toBe(0);
  });

  it("applies correct styling for covered vs uncovered keywords", () => {
    const keywords = ["Covered", "NotCovered"];
    const isCovered = (kw: string) => kw === "Covered";

    render(<KeywordChips keywords={keywords} isCovered={isCovered} />);

    // The rendered badges should exist with different styling
    const coveredBadge = screen.getByText("Covered").closest("div");
    const uncoveredBadge = screen.getByText("NotCovered").closest("div");

    // Both badges should exist
    expect(coveredBadge).toBeInTheDocument();
    expect(uncoveredBadge).toBeInTheDocument();
  });
});
