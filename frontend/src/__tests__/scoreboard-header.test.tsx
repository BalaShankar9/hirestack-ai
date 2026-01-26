import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreboardHeader } from "@/components/workspace/scoreboard-header";

describe("ScoreboardHeader", () => {
  it("renders key metrics and top fix", () => {
    render(
      <ScoreboardHeader
        title="Senior Frontend Engineer"
        subtitle="@ ExampleCo"
        scorecard={{
          match: 72,
          atsReadiness: 64,
          recruiterScan: 58,
          evidenceStrength: 40,
          topFix: "Add quantified proof for React performance work.",
          updatedAt: Date.now(),
        }}
      />
    );

    expect(screen.getByText("Senior Frontend Engineer")).toBeInTheDocument();
    expect(screen.getByText("@ ExampleCo")).toBeInTheDocument();
    expect(screen.getByText(/Add quantified proof/i)).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("64%")).toBeInTheDocument();
    expect(screen.getByText("58%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });
});

