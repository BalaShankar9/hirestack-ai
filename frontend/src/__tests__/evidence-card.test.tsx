import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvidenceCard } from "@/components/workspace/evidence-card";
import type { EvidenceDoc } from "@/lib/firestore";

afterEach(() => {
  cleanup();
});

const mockLinkEvidence: EvidenceDoc = {
  id: "ev1",
  userId: "u1",
  kind: "link",
  title: "React Performance Optimization Blog",
  description: "Deep dive into React rendering optimizations",
  url: "https://example.com/react-perf",
  skills: ["React", "Performance", "TypeScript"],
  tools: ["Chrome DevTools", "React Profiler"],
  tags: ["frontend", "optimization"],
  createdAt: Date.now(),
  updatedAt: Date.now(),
};

const mockFileEvidence: EvidenceDoc = {
  id: "ev2",
  userId: "u1",
  kind: "file",
  title: "System Design Document",
  description: "Architecture for distributed cache",
  storagePath: "/files/design.pdf",
  storageUrl: "https://storage.example.com/files/design.pdf",
  mimeType: "application/pdf",
  skills: ["System Design", "Distributed Systems"],
  tools: ["AWS", "Redis"],
  tags: ["architecture", "backend"],
  createdAt: Date.now(),
  updatedAt: Date.now(),
};

describe("EvidenceCard", () => {
  it("renders link evidence with title and description", () => {
    render(<EvidenceCard evidence={mockLinkEvidence} />);

    expect(screen.getByText("React Performance Optimization Blog")).toBeInTheDocument();
    expect(screen.getByText("Deep dive into React rendering optimizations")).toBeInTheDocument();
  });

  it("renders file evidence with title and description", () => {
    render(<EvidenceCard evidence={mockFileEvidence} />);

    expect(screen.getByText("System Design Document")).toBeInTheDocument();
    expect(screen.getByText("Architecture for distributed cache")).toBeInTheDocument();
  });

  it("renders skills badges", () => {
    render(<EvidenceCard evidence={mockLinkEvidence} />);

    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("Performance")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
  });

  it("renders tools badges", () => {
    render(<EvidenceCard evidence={mockLinkEvidence} />);

    expect(screen.getByText("Chrome DevTools")).toBeInTheDocument();
    expect(screen.getByText("React Profiler")).toBeInTheDocument();
  });

  it("renders tags badges", () => {
    render(<EvidenceCard evidence={mockLinkEvidence} />);

    expect(screen.getByText("frontend")).toBeInTheDocument();
    expect(screen.getByText("optimization")).toBeInTheDocument();
  });

  it("calls onUse when Use in CV button is clicked", () => {
    const onUse = vi.fn();
    const { container } = render(<EvidenceCard evidence={mockLinkEvidence} onUse={onUse} />);

    const buttons = container.querySelectorAll("button");
    const useButton = Array.from(buttons).find(btn => btn.textContent?.includes("Use in CV"));
    if (useButton) useButton.click();
    expect(onUse).toHaveBeenCalledWith(mockLinkEvidence);
  });

  it("disables Use in CV button when onUse is not provided", () => {
    const { container } = render(<EvidenceCard evidence={mockLinkEvidence} />);

    const buttons = container.querySelectorAll("button");
    const useButton = Array.from(buttons).find(btn => btn.textContent?.includes("Use in CV"));
    expect(useButton).toHaveAttribute("disabled");
  });

  it("calls onOpen when Open button is clicked", () => {
    const onOpen = vi.fn();
    const { container } = render(<EvidenceCard evidence={mockLinkEvidence} onOpen={onOpen} />);

    const buttons = container.querySelectorAll("button");
    const openButton = Array.from(buttons).find(btn => btn.textContent === "Open");
    if (openButton) openButton.click();
    expect(onOpen).toHaveBeenCalledWith(mockLinkEvidence);
  });

  it("renders evidence without skills, tools, or tags", () => {
    const minimalEvidence: EvidenceDoc = {
      id: "ev3",
      userId: "u1",
      kind: "link",
      title: "Minimal Evidence",
      url: "https://example.com",
      skills: [],
      tools: [],
      tags: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    render(<EvidenceCard evidence={minimalEvidence} />);

    expect(screen.getByText("Minimal Evidence")).toBeInTheDocument();
  });

  it("truncates skills to first 6 when more are provided", () => {
    const manySkillsEvidence: EvidenceDoc = {
      ...mockLinkEvidence,
      id: "ev4",
      skills: ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6", "Skill7", "Skill8"],
    };

    const { container } = render(<EvidenceCard evidence={manySkillsEvidence} />);

    expect(container.textContent).toContain("Skill1");
    expect(container.textContent).toContain("Skill6");
    expect(container.textContent).not.toContain("Skill7");
    expect(container.textContent).not.toContain("Skill8");
  });
});
