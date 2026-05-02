import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CandidateValidationPanel } from "@/components/workspace/candidate-validation-panel";
import type {
  CandidateValidationReport,
  CandidateValidationClaim,
} from "@/lib/firestore";

afterEach(() => cleanup());

const _claim = (overrides: Partial<CandidateValidationClaim> = {}): CandidateValidationClaim => ({
  claim: "5y python",
  validator: "github_commits",
  status: "verified",
  detail: "first commit 2019-03",
  ...overrides,
});

const _report = (claims: CandidateValidationClaim[]): CandidateValidationReport => ({
  claims,
  verified_count: claims.filter((c) => c.status === "verified").length,
  conflicted_count: claims.filter((c) => c.status === "conflicted").length,
});

describe("CandidateValidationPanel", () => {
  it("renders nothing when report is undefined", () => {
    const { container } = render(<CandidateValidationPanel report={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when report is null", () => {
    const { container } = render(<CandidateValidationPanel report={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when claims list is empty", () => {
    const { container } = render(
      <CandidateValidationPanel report={_report([])} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the header summary with correct counts", () => {
    render(
      <CandidateValidationPanel
        report={_report([
          _claim({ status: "verified" }),
          _claim({ status: "verified" }),
          _claim({ status: "conflicted" }),
          _claim({ status: "unverified" }),
        ])}
      />,
    );
    const summary = screen.getByTestId("atlas-validation-summary");
    expect(summary.textContent).toContain("2 verified");
    expect(summary.textContent).toContain("1 conflicted");
    expect(summary.textContent).toContain("4 total");
  });

  it("renders one row per claim", () => {
    render(
      <CandidateValidationPanel
        report={_report([
          _claim({ claim: "A" }),
          _claim({ claim: "B" }),
          _claim({ claim: "C" }),
        ])}
      />,
    );
    expect(screen.getAllByTestId("atlas-validation-claim")).toHaveLength(3);
  });

  it("sorts conflicted claims first, then unverified, then verified", () => {
    render(
      <CandidateValidationPanel
        report={_report([
          _claim({ claim: "ok-1", status: "verified" }),
          _claim({ claim: "fishy", status: "conflicted" }),
          _claim({ claim: "maybe", status: "unverified" }),
          _claim({ claim: "ok-2", status: "verified" }),
        ])}
      />,
    );
    const rows = screen.getAllByTestId("atlas-validation-claim");
    expect(rows[0].getAttribute("data-status")).toBe("conflicted");
    expect(rows[1].getAttribute("data-status")).toBe("unverified");
    expect(rows[2].getAttribute("data-status")).toBe("verified");
    expect(rows[3].getAttribute("data-status")).toBe("verified");
  });

  it("renders the claim text, validator and detail", () => {
    render(
      <CandidateValidationPanel
        report={_report([
          _claim({
            claim: "worked at Stripe 2020-2024",
            validator: "company_exists",
            status: "verified",
            detail: "wikidata Q5953982",
          }),
        ])}
      />,
    );
    expect(screen.getByText("worked at Stripe 2020-2024")).toBeInTheDocument();
    expect(screen.getByText("via company_exists")).toBeInTheDocument();
    expect(screen.getByText("wikidata Q5953982")).toBeInTheDocument();
  });

  it("renders the status badge text for each row", () => {
    render(
      <CandidateValidationPanel
        report={_report([
          _claim({ claim: "C", status: "conflicted" }),
          _claim({ claim: "U", status: "unverified" }),
          _claim({ claim: "V", status: "verified" }),
        ])}
      />,
    );
    expect(screen.getByText("conflicted")).toBeInTheDocument();
    expect(screen.getByText("unverified")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
  });

  it("falls back to '(no claim text)' for empty claim strings", () => {
    render(
      <CandidateValidationPanel
        report={_report([_claim({ claim: "" })])}
      />,
    );
    expect(screen.getByText("(no claim text)")).toBeInTheDocument();
  });

  it("hides the detail line when detail is empty", () => {
    render(
      <CandidateValidationPanel
        report={_report([_claim({ claim: "X", detail: "" })])}
      />,
    );
    // The known fixture detail must not appear when detail is blank.
    expect(screen.queryByText("first commit 2019-03")).not.toBeInTheDocument();
    expect(screen.getByTestId("atlas-validation-claim")).toBeInTheDocument();
  });

  it("includes 'via <validator>' for each row", () => {
    render(
      <CandidateValidationPanel
        report={_report([_claim({ claim: "X", validator: "date_consistency" })])}
      />,
    );
    expect(screen.getByText("via date_consistency")).toBeInTheDocument();
  });

  it("uses verified_count / conflicted_count from the report (not recomputed)", () => {
    // Trust the wire counts so we don't double-count if the backend
    // ever applies extra logic the FE doesn't know about.
    render(
      <CandidateValidationPanel
        report={{
          claims: [_claim({ status: "verified" })],
          verified_count: 99,
          conflicted_count: 7,
        }}
      />,
    );
    const summary = screen.getByTestId("atlas-validation-summary");
    expect(summary.textContent).toContain("99 verified");
    expect(summary.textContent).toContain("7 conflicted");
  });
});
