import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReadyToApply } from "@/components/dashboard/ready-to-apply";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

describe("ReadyToApply", () => {
  it("prioritizes ready draft workspaces and keeps in-flight watchlist items visible", () => {
    render(
      <ReadyToApply
        apps={[
          {
            id: "app-ready",
            userId: "u1",
            title: "Staff Engineer",
            status: "draft",
            createdAt: Date.now(),
            updatedAt: Date.now(),
            confirmedFacts: {
              jobTitle: "Staff Engineer",
              jdText: "JD",
              jdQuality: { score: 90, flags: [], summary: "" },
              resume: {},
              company: "Acme",
              source: "tracked_company_auto_prep",
              auto_prep: { fit_score: 4.8 },
            },
            modules: {
              benchmark: { state: "ready" },
              gaps: { state: "ready" },
              learningPlan: { state: "idle" },
              cv: { state: "ready" },
              resume: { state: "idle" },
              coverLetter: { state: "ready" },
              personalStatement: { state: "idle" },
              portfolio: { state: "idle" },
              scorecard: { state: "ready" },
            },
            cvHtml: "<p>CV</p>",
            coverLetterHtml: "<p>CL</p>",
            scorecard: { overall: 88, dimensions: [] },
            scores: { fit: 4.8 },
          },
          {
            id: "app-generating",
            userId: "u1",
            title: "Platform Engineer",
            status: "draft",
            createdAt: Date.now(),
            updatedAt: Date.now() - 10_000,
            confirmedFacts: {
              jobTitle: "Platform Engineer",
              jdText: "JD",
              jdQuality: { score: 85, flags: [], summary: "" },
              resume: {},
              company: "Beta",
              source: "tracked_company_auto_prep",
              auto_prep: { fit_score: 4.5 },
            },
            modules: {
              benchmark: { state: "queued" },
              gaps: { state: "queued" },
              learningPlan: { state: "idle" },
              cv: { state: "generating" },
              resume: { state: "idle" },
              coverLetter: { state: "idle" },
              personalStatement: { state: "idle" },
              portfolio: { state: "idle" },
              scorecard: { state: "idle" },
            },
            scores: { fit: 4.5 },
          },
          {
            id: "app-archived",
            userId: "u1",
            title: "Old Role",
            status: "archived",
            createdAt: Date.now(),
            updatedAt: Date.now(),
            confirmedFacts: {
              jobTitle: "Old Role",
              jdText: "JD",
              jdQuality: { score: 80, flags: [], summary: "" },
              resume: {},
            },
            modules: {
              benchmark: { state: "ready" },
              gaps: { state: "ready" },
              learningPlan: { state: "idle" },
              cv: { state: "ready" },
              resume: { state: "idle" },
              coverLetter: { state: "ready" },
              personalStatement: { state: "idle" },
              portfolio: { state: "idle" },
              scorecard: { state: "ready" },
            },
            cvHtml: "<p>CV</p>",
            coverLetterHtml: "<p>CL</p>",
            scorecard: { overall: 80, dimensions: [] },
          },
        ] as any}
      />,
    );

    expect(screen.getByText(/ready to apply/i)).toBeInTheDocument();
    expect(screen.getByText(/1 ready now · 1 still generating/i)).toBeInTheDocument();
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    expect(screen.getByText("Platform Engineer")).toBeInTheDocument();
    expect(screen.queryByText("Old Role")).not.toBeInTheDocument();
    expect(screen.getAllByText(/ready now/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/generating/i).length).toBeGreaterThan(0);
  });
});