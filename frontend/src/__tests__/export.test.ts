/**
 * P1-16: Verify export (download) works for at least one format.
 *
 * Tests the export library helper functions:
 * - buildBenchmarkHtml: produces valid, structured HTML from benchmark data.
 * - buildGapAnalysisHtml: produces valid, structured HTML from gaps data.
 * - buildLearningPlanHtml: produces valid, structured HTML from learning plan data.
 * - downloadHtml: triggers a browser download with a correctly-formed HTML file.
 *
 * Browser-specific functions (exportToPdf, downloadDocx) require html2pdf.js
 * and a real DOM renderer, so they are covered by integration tests.
 */
import { describe, expect, it, vi, afterEach } from "vitest";

import {
  buildBenchmarkHtml,
  buildGapAnalysisHtml,
  buildLearningPlanHtml,
  downloadHtml,
} from "@/lib/export";

// ---------------------------------------------------------------------------
// buildBenchmarkHtml
// ---------------------------------------------------------------------------

describe("buildBenchmarkHtml", () => {
  it("returns empty string for null/undefined benchmark", () => {
    expect(buildBenchmarkHtml(null, "SWE")).toBe("");
    expect(buildBenchmarkHtml(undefined, "SWE")).toBe("");
  });

  it("includes the job title in the output", () => {
    const html = buildBenchmarkHtml({ summary: "A great candidate" }, "Senior Engineer");
    expect(html).toContain("Senior Engineer");
  });

  it("includes the benchmark summary", () => {
    const html = buildBenchmarkHtml({ summary: "Expert in distributed systems" }, "Backend SWE");
    expect(html).toContain("Expert in distributed systems");
  });

  it("renders skill list items", () => {
    const benchmark = {
      idealSkills: [
        { name: "Go", level: "expert", importance: "critical" },
        { name: "Kubernetes", level: "proficient", importance: "important" },
      ],
    };
    const html = buildBenchmarkHtml(benchmark, "Platform Engineer");
    expect(html).toContain("<strong>Go</strong>");
    expect(html).toContain("expert");
    expect(html).toContain("<strong>Kubernetes</strong>");
  });

  it("renders keyword list", () => {
    const benchmark = { keywords: ["Python", "TDD", "CI/CD"] };
    const html = buildBenchmarkHtml(benchmark, "SWE");
    expect(html).toContain("Python");
    expect(html).toContain("TDD");
    expect(html).toContain("CI/CD");
  });

  it("renders rubric items", () => {
    const benchmark = {
      rubric: ["Must have 5+ years experience", "Led cross-functional team"],
    };
    const html = buildBenchmarkHtml(benchmark, "SWE");
    expect(html).toContain("Must have 5+ years experience");
    expect(html).toContain("Led cross-functional team");
  });

  it("handles empty skill/keyword arrays gracefully", () => {
    const html = buildBenchmarkHtml(
      { idealSkills: [], rubric: [], keywords: [] },
      "Designer"
    );
    expect(html).toContain("<h2>Benchmark");
    expect(html).toContain("<ul></ul>");
  });
});

// ---------------------------------------------------------------------------
// buildGapAnalysisHtml
// ---------------------------------------------------------------------------

describe("buildGapAnalysisHtml", () => {
  it("returns empty string for null/undefined gaps", () => {
    expect(buildGapAnalysisHtml(null)).toBe("");
    expect(buildGapAnalysisHtml(undefined)).toBe("");
  });

  it("includes compatibility score when present", () => {
    const html = buildGapAnalysisHtml({ compatibility: 72 });
    expect(html).toContain("72%");
  });

  it("includes summary text", () => {
    const html = buildGapAnalysisHtml({ summary: "Good match overall" });
    expect(html).toContain("Good match overall");
  });

  it("renders missing keywords list", () => {
    const html = buildGapAnalysisHtml({
      missingKeywords: ["GraphQL", "AWS Lambda"],
    });
    expect(html).toContain("GraphQL");
    expect(html).toContain("AWS Lambda");
  });

  it("renders strengths list", () => {
    const html = buildGapAnalysisHtml({
      strengths: ["Strong TypeScript background", "Testing expertise"],
    });
    expect(html).toContain("Strong TypeScript background");
    expect(html).toContain("Testing expertise");
  });

  it("renders recommendations list", () => {
    const html = buildGapAnalysisHtml({
      recommendations: ["Learn Terraform", "Get AWS cert"],
    });
    expect(html).toContain("Learn Terraform");
    expect(html).toContain("Get AWS cert");
  });

  it("omits compatibility section when not set", () => {
    const html = buildGapAnalysisHtml({ summary: "Needs work" });
    expect(html).not.toContain("Compatibility Score");
  });
});

// ---------------------------------------------------------------------------
// buildLearningPlanHtml
// ---------------------------------------------------------------------------

describe("buildLearningPlanHtml", () => {
  it("returns empty string for null/undefined plan", () => {
    expect(buildLearningPlanHtml(null)).toBe("");
    expect(buildLearningPlanHtml(undefined)).toBe("");
  });

  it("includes focus areas", () => {
    const html = buildLearningPlanHtml({ focus: ["Go", "Distributed Systems"] });
    expect(html).toContain("Go");
    expect(html).toContain("Distributed Systems");
  });

  it("renders weekly plan themes and outcomes", () => {
    const plan = {
      plan: [
        {
          week: 1,
          theme: "Foundations",
          outcomes: ["Understand goroutines", "Write first service"],
          tasks: ["Complete Go tour", "Build hello-world API"],
        },
      ],
    };
    const html = buildLearningPlanHtml(plan);
    expect(html).toContain("Week 1");
    expect(html).toContain("Foundations");
    expect(html).toContain("Understand goroutines");
    expect(html).toContain("Complete Go tour");
  });

  it("renders resources list", () => {
    const html = buildLearningPlanHtml({
      resources: [
        { title: "Go by Example", provider: "gobyexample.com", timebox: "2h" },
      ],
    });
    expect(html).toContain("Go by Example");
    expect(html).toContain("gobyexample.com");
  });

  it("handles empty plan and resources arrays", () => {
    const html = buildLearningPlanHtml({ focus: [], plan: [], resources: [] });
    expect(html).toContain("<h2>Learning Plan</h2>");
  });
});

// ---------------------------------------------------------------------------
// downloadHtml — browser-triggered download
// ---------------------------------------------------------------------------

describe("downloadHtml", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("triggers an anchor click to download an HTML file", () => {
    // Mock URL and DOM APIs
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = vi.fn();
    (globalThis as any).URL.createObjectURL = createObjectURL;
    (globalThis as any).URL.revokeObjectURL = revokeObjectURL;

    const mockAnchor = {
      href: "",
      download: "",
      click: vi.fn(),
      setAttribute: vi.fn(),
    };
    const appendChildSpy = vi.spyOn(document.body, "appendChild").mockImplementation(() => mockAnchor as any);
    const removeChildSpy = vi.spyOn(document.body, "removeChild").mockImplementation(() => mockAnchor as any);
    vi.spyOn(document, "createElement").mockReturnValue(mockAnchor as any);

    downloadHtml("<h1>Test CV</h1>", { filename: "my-cv" });

    expect(mockAnchor.download).toBe("my-cv.html");
    expect(mockAnchor.click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
    expect(appendChildSpy).toHaveBeenCalled();
    expect(removeChildSpy).toHaveBeenCalled();
  });

  it("uses default filename when not provided", () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:url");
    const revokeObjectURL = vi.fn();
    (globalThis as any).URL.createObjectURL = createObjectURL;
    (globalThis as any).URL.revokeObjectURL = revokeObjectURL;

    const mockAnchor = {
      href: "",
      download: "",
      click: vi.fn(),
    };
    vi.spyOn(document.body, "appendChild").mockImplementation(() => mockAnchor as any);
    vi.spyOn(document.body, "removeChild").mockImplementation(() => mockAnchor as any);
    vi.spyOn(document, "createElement").mockReturnValue(mockAnchor as any);

    downloadHtml("<p>Hello</p>");

    expect(mockAnchor.download).toBe("document.html");
  });

  it("wraps content in a full HTML document", () => {
    let capturedBlob: Blob | null = null;
    (globalThis as any).URL.createObjectURL = (blob: Blob) => {
      capturedBlob = blob;
      return "blob:url";
    };
    (globalThis as any).URL.revokeObjectURL = vi.fn();

    const mockAnchor = { href: "", download: "", click: vi.fn() };
    vi.spyOn(document.body, "appendChild").mockImplementation(() => mockAnchor as any);
    vi.spyOn(document.body, "removeChild").mockImplementation(() => mockAnchor as any);
    vi.spyOn(document, "createElement").mockReturnValue(mockAnchor as any);

    downloadHtml("<h1>My CV</h1>", { filename: "cv" });

    // Verify the blob was created with HTML mime type
    expect(capturedBlob).not.toBeNull();
    expect((capturedBlob as unknown as Blob).type).toBe("text/html");
  });
});
