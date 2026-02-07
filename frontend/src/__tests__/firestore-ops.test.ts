import { describe, expect, it, vi, beforeAll } from "vitest";

// Mock Supabase before importing ops
vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
    from: vi.fn(() => ({
      select: vi.fn().mockReturnThis(),
      insert: vi.fn().mockReturnThis(),
      update: vi.fn().mockReturnThis(),
      delete: vi.fn().mockReturnThis(),
      upsert: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockReturnThis(),
      maybeSingle: vi.fn(() => Promise.resolve({ data: null, error: null })),
      single: vi.fn(() => Promise.resolve({ data: null, error: null })),
    })),
    storage: {
      from: vi.fn(() => ({
        upload: vi.fn(() => Promise.resolve({ error: null })),
        getPublicUrl: vi.fn(() => ({ data: { publicUrl: "https://example.com/file" } })),
      })),
    },
    channel: vi.fn(() => ({
      on: vi.fn().mockReturnThis(),
      subscribe: vi.fn(),
    })),
    removeChannel: vi.fn(),
  })),
}));

import {
  computeJDQuality,
  extractKeywords,
  computeMatchScore,
  computeDocCoverageScore,
  deriveTopFix,
  buildBenchmark,
  buildGaps,
  buildLearningPlan,
  buildScorecard,
  buildCoachActions,
  seedCvHtml,
  seedCoverLetterHtml,
  uid,
  emptyDocModule,
} from "@/lib/firestore/ops";
import type { ConfirmedFacts, JDQuality } from "@/lib/firestore/models";

describe("JD Quality Analysis", () => {
  describe("computeJDQuality", () => {
    it("returns low score for short JD", () => {
      const result = computeJDQuality("Software Engineer at TechCo");
      expect(result.score).toBeLessThan(50);
      expect(result.issues.length).toBeGreaterThan(0);
      expect(result.suggestions.length).toBeGreaterThan(0);
    });

    it("returns higher score for comprehensive JD", () => {
      const fullJD = `
        Senior Frontend Engineer at TechCorp

        Responsibilities:
        - Build and maintain React applications with TypeScript
        - Lead performance optimization initiatives
        - Collaborate with backend engineers on API design
        - Mentor junior developers and conduct code reviews

        Requirements:
        - 5+ years of experience with JavaScript/TypeScript
        - Strong knowledge of React, Next.js, and state management
        - Experience with testing frameworks like Jest and Playwright
        - Excellent communication skills

        Tech Stack:
        - React, Next.js, TypeScript
        - GraphQL, REST APIs
        - Docker, Kubernetes
        - AWS, GCP
      `;
      const result = computeJDQuality(fullJD);
      expect(result.score).toBeGreaterThan(60);
    });

    it("detects missing responsibilities section", () => {
      const jdWithoutResponsibilities = `
        Software Engineer

        Requirements:
        - JavaScript experience
        - React knowledge
      `;
      const result = computeJDQuality(jdWithoutResponsibilities);
      expect(result.issues.some((i: string) => i.toLowerCase().includes("responsibilit"))).toBe(true);
    });

    it("detects missing requirements section", () => {
      const jdWithoutRequirements = `
        Software Engineer

        Responsibilities:
        - Build features
        - Fix bugs
      `;
      const result = computeJDQuality(jdWithoutRequirements);
      expect(result.issues.some((i: string) => i.toLowerCase().includes("requirement"))).toBe(true);
    });

    it("detects missing bullet points", () => {
      const jdWithoutBullets = "Software Engineer at TechCo working on React applications using TypeScript for web development";
      const result = computeJDQuality(jdWithoutBullets);
      expect(result.issues.some((i: string) => i.toLowerCase().includes("bullet"))).toBe(true);
    });
  });
});

describe("Keyword Extraction", () => {
  describe("extractKeywords", () => {
    it("extracts known skills from text", () => {
      const text = "Experience with React, TypeScript, and Node.js required";
      const keywords = extractKeywords(text);
      expect(keywords).toContain("react");
      expect(keywords).toContain("typescript");
      expect(keywords).toContain("node");
    });

    it("filters out stopwords", () => {
      const text = "The team working with experience and skills for this role";
      const keywords = extractKeywords(text);
      expect(keywords).not.toContain("the");
      expect(keywords).not.toContain("and");
      expect(keywords).not.toContain("for");
      expect(keywords).not.toContain("with");
    });

    it("respects max limit", () => {
      const text = `
        React TypeScript Node Python FastAPI SQL Postgres Firebase Docker Kubernetes
        Tailwind Jest Vitest Playwright GraphQL REST microservices machine learning
      `;
      const keywords = extractKeywords(text, 5);
      expect(keywords.length).toBeLessThanOrEqual(5);
    });

    it("handles empty text", () => {
      const keywords = extractKeywords("");
      expect(keywords).toEqual([]);
    });

    it("handles text with no valid keywords", () => {
      const keywords = extractKeywords("the and for with");
      expect(keywords.length).toBe(0);
    });
  });
});

describe("Match Score Calculation", () => {
  describe("computeMatchScore", () => {
    it("returns 0 when no confirmed facts", () => {
      const score = computeMatchScore(null, ["react", "typescript"]);
      expect(score).toBe(0);
    });

    it("returns 0 when no keywords", () => {
      const facts: ConfirmedFacts = {
        jobTitle: "Engineer",
        jdText: "React TypeScript role",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "React TypeScript experience" },
      };
      const score = computeMatchScore(facts, []);
      expect(score).toBe(0);
    });

    it("calculates correct match percentage", () => {
      const facts: ConfirmedFacts = {
        jobTitle: "Engineer",
        jdText: "React TypeScript Node role",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "React TypeScript experience" },
      };
      const keywords = ["react", "typescript", "python", "fastapi"];
      const score = computeMatchScore(facts, keywords);
      expect(score).toBe(50); // 2 out of 4 keywords match
    });

    it("returns 100 when all keywords are covered", () => {
      const facts: ConfirmedFacts = {
        jobTitle: "Engineer",
        jdText: "React TypeScript",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "React TypeScript developer" },
      };
      const keywords = ["react", "typescript"];
      const score = computeMatchScore(facts, keywords);
      expect(score).toBe(100);
    });
  });
});

describe("Document Coverage Score", () => {
  describe("computeDocCoverageScore", () => {
    it("returns 0 for empty document", () => {
      const score = computeDocCoverageScore("", ["react", "typescript"]);
      expect(score).toBe(0);
    });

    it("returns 0 when no keywords", () => {
      const score = computeDocCoverageScore("<p>Some content</p>", []);
      expect(score).toBe(0);
    });

    it("calculates correct coverage percentage", () => {
      const html = "<p>Experience with React and TypeScript development</p>";
      const keywords = ["react", "typescript", "python", "node"];
      const score = computeDocCoverageScore(html, keywords);
      expect(score).toBe(50); // 2 out of 4 keywords found
    });

    it("strips HTML tags before checking", () => {
      const html = "<h1>React</h1><p>TypeScript</p><ul><li>Node.js</li></ul>";
      const keywords = ["react", "typescript", "node"];
      const score = computeDocCoverageScore(html, keywords);
      expect(score).toBe(100);
    });
  });
});

describe("Top Fix Derivation", () => {
  describe("deriveTopFix", () => {
    it("suggests adding proof for first missing keyword", () => {
      const fix = deriveTopFix(["React", "TypeScript"], { score: 75, issues: [], suggestions: [] });
      expect(fix).toContain("React");
      expect(fix.toLowerCase()).toContain("proof");
    });

    it("suggests improving JD quality when no missing keywords but low quality", () => {
      const fix = deriveTopFix([], { score: 40, issues: ["Short JD"], suggestions: [] });
      expect(fix.toLowerCase()).toContain("jd");
    });

    it("suggests tightening summary when no obvious fixes needed", () => {
      const fix = deriveTopFix([], { score: 80, issues: [], suggestions: [] });
      expect(fix.toLowerCase()).toContain("summary");
    });
  });
});

describe("Module Builders", () => {
  describe("buildBenchmark", () => {
    it("creates benchmark with summary and rubric", () => {
      const benchmark = buildBenchmark("Senior Engineer", "TechCo", ["react", "typescript"]);

      expect(benchmark.summary).toContain("Senior Engineer");
      expect(benchmark.summary).toContain("TechCo");
      expect(benchmark.keywords).toEqual(["react", "typescript"]);
      expect(benchmark.rubric.length).toBeGreaterThan(0);
      expect(benchmark.createdAt).toBeDefined();
    });

    it("handles missing company", () => {
      const benchmark = buildBenchmark("Senior Engineer", undefined, ["react"]);
      expect(benchmark.summary).toContain("Senior Engineer");
      expect(benchmark.summary).not.toContain("undefined");
    });
  });

  describe("buildGaps", () => {
    it("identifies missing keywords", () => {
      const facts: ConfirmedFacts = {
        jobTitle: "Engineer",
        jdText: "React TypeScript Python FastAPI",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "Experience with React and TypeScript development" },
      };
      const gaps = buildGaps(facts, ["react", "typescript", "python", "fastapi"]);

      expect(gaps.missingKeywords).toContain("python");
      expect(gaps.missingKeywords).toContain("fastapi");
      expect(gaps.missingKeywords).not.toContain("react");
      expect(gaps.missingKeywords).not.toContain("typescript");
    });

    it("identifies strengths from confirmed facts", () => {
      const facts: ConfirmedFacts = {
        jobTitle: "Engineer",
        jdText: "React developer",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "Expert in React and TypeScript and Node.js" },
      };
      const gaps = buildGaps(facts, ["react"]);

      expect(gaps.strengths.length).toBeGreaterThan(0);
    });

    it("includes recommendations", () => {
      const gaps = buildGaps(null, ["react", "typescript"]);
      expect(gaps.recommendations.length).toBeGreaterThan(0);
    });
  });

  describe("buildLearningPlan", () => {
    it("creates 4-week plan", () => {
      const plan = buildLearningPlan(["React", "TypeScript"]);

      expect(plan.plan.length).toBe(4);
      expect(plan.plan[0].week).toBe(1);
      expect(plan.plan[3].week).toBe(4);
    });

    it("includes focus areas from missing keywords", () => {
      const plan = buildLearningPlan(["React", "TypeScript", "Node.js"]);

      expect(plan.focus).toContain("React");
      expect(plan.focus).toContain("TypeScript");
      expect(plan.focus).toContain("Node.js");
    });

    it("creates resources for each focus skill", () => {
      const plan = buildLearningPlan(["React", "TypeScript"]);

      expect(plan.resources.length).toBe(2);
      expect(plan.resources[0].skill).toBe("React");
      expect(plan.resources[1].skill).toBe("TypeScript");
    });

    it("handles empty missing keywords", () => {
      const plan = buildLearningPlan([]);

      expect(plan.plan.length).toBe(4);
      expect(plan.focus.length).toBe(0);
    });
  });
});

describe("Scorecard Builder", () => {
  describe("buildScorecard", () => {
    it("creates scorecard with all metrics", () => {
      const scorecard = buildScorecard({
        match: 75,
        ats: 80,
        scan: 65,
        evidence: 50,
        topFix: "Add proof for React",
      });

      expect(scorecard.match).toBe(75);
      expect(scorecard.atsReadiness).toBe(80);
      expect(scorecard.recruiterScan).toBe(65);
      expect(scorecard.evidenceStrength).toBe(50);
      expect(scorecard.topFix).toBe("Add proof for React");
      expect(scorecard.updatedAt).toBeDefined();
    });

    it("clamps values to 0-100 range", () => {
      const scorecard = buildScorecard({
        match: 150,
        ats: -20,
        scan: 50,
        evidence: 200,
        topFix: "Test",
      });

      expect(scorecard.match).toBe(100);
      expect(scorecard.atsReadiness).toBe(0);
      expect(scorecard.recruiterScan).toBe(50);
      expect(scorecard.evidenceStrength).toBe(100);
    });
  });
});

describe("Coach Actions Builder", () => {
  describe("buildCoachActions", () => {
    it("returns lock facts action when facts not locked", () => {
      const actions = buildCoachActions({
        missingKeywords: [],
        factsLocked: false,
        evidenceCount: 0,
      });

      expect(actions.length).toBe(1);
      expect(actions[0].kind).toBe("review");
      expect(actions[0].title.toLowerCase()).toContain("lock");
    });

    it("returns collect evidence action when no evidence", () => {
      const actions = buildCoachActions({
        missingKeywords: [],
        factsLocked: true,
        evidenceCount: 0,
      });

      expect(actions.length).toBe(1);
      expect(actions[0].kind).toBe("collect");
    });

    it("returns fix action when missing keywords", () => {
      const actions = buildCoachActions({
        missingKeywords: ["React", "TypeScript"],
        factsLocked: true,
        evidenceCount: 5,
      });

      expect(actions.length).toBe(1);
      expect(actions[0].kind).toBe("fix");
      expect(actions[0].title).toContain("React");
    });

    it("returns snapshot action when all good", () => {
      const actions = buildCoachActions({
        missingKeywords: [],
        factsLocked: true,
        evidenceCount: 5,
      });

      expect(actions.length).toBe(1);
      expect(actions[0].kind).toBe("write");
      expect(actions[0].title.toLowerCase()).toContain("snapshot");
    });
  });
});

describe("Document Seed Generators", () => {
  describe("seedCvHtml", () => {
    it("includes user name and headline", () => {
      // seedCvHtml reads fullName/headline via (facts as any) for forward compat
      const facts = {
        jobTitle: "Frontend Engineer",
        jdText: "React role",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "" },
        fullName: "John Doe",
        headline: "Senior Engineer",
      } as any;
      const html = seedCvHtml(facts, "Frontend Engineer", "TechCo", ["react"]);

      expect(html).toContain("John Doe");
      expect(html).toContain("Senior Engineer");
    });

    it("includes role keywords section", () => {
      const html = seedCvHtml(null, "Frontend Engineer", "TechCo", ["react", "typescript"]);

      expect(html).toContain("Role Keywords");
      expect(html).toContain("react");
      expect(html).toContain("typescript");
    });

    it("includes proof hooks section", () => {
      const html = seedCvHtml(null, "Frontend Engineer", "TechCo", ["react"]);

      expect(html).toContain("Proof Hooks");
    });

    it("includes base resume when provided", () => {
      const baseResume = "<p>My original resume content</p>";
      const html = seedCvHtml(null, "Frontend Engineer", "TechCo", ["react"], baseResume);

      expect(html).toContain("Base Resume");
      expect(html).toContain("My original resume content");
    });
  });

  describe("seedCoverLetterHtml", () => {
    it("includes cover letter structure", () => {
      const facts = {
        jobTitle: "Frontend Engineer",
        jdText: "React role",
        jdQuality: { score: 80, flags: [], summary: "" },
        resume: { text: "" },
        fullName: "John Doe",
      } as any;
      const html = seedCoverLetterHtml(facts, "Frontend Engineer", "TechCo", ["react"]);

      expect(html).toContain("Cover Letter");
      expect(html).toContain("TechCo");
      expect(html).toContain("John Doe");
    });

    it("includes keywords in narrative", () => {
      const html = seedCoverLetterHtml(null, "Frontend Engineer", "TechCo", ["react", "typescript", "node"]);

      expect(html).toContain("react");
    });
  });
});

describe("Utility Functions", () => {
  describe("uid", () => {
    it("generates unique IDs with prefix", () => {
      const id1 = uid("app");
      const id2 = uid("app");

      expect(id1).toMatch(/^app_/);
      expect(id2).toMatch(/^app_/);
      expect(id1).not.toBe(id2);
    });

    it("uses default prefix when not provided", () => {
      const id = uid();
      expect(id).toMatch(/^id_/);
    });
  });

  describe("emptyDocModule", () => {
    it("creates empty doc module with default html", () => {
      const doc = emptyDocModule();

      expect(doc.contentHtml).toBe("");
      expect(doc.versions).toEqual([]);
      expect(doc.updatedAt).toBeDefined();
    });

    it("creates doc module with seed html", () => {
      const doc = emptyDocModule("<p>Initial content</p>");

      expect(doc.contentHtml).toBe("<p>Initial content</p>");
    });
  });
});
