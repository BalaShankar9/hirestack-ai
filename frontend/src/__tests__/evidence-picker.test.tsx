/**
 * P1-15: Verify evidence picker can insert evidence into a document.
 *
 * Tests that EvidencePicker:
 * - Renders the search input and evidence items.
 * - Filters evidence by the search query.
 * - Calls onPick with the selected evidence when "Use" is clicked.
 * - Closes the dialog after picking.
 * - Shows an empty state when no matches are found.
 */
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvidencePicker } from "@/components/workspace/evidence-picker";

afterEach(() => {
  cleanup();
});

const ev1 = {
  id: "ev1",
  userId: "u1",
  applicationId: null,
  kind: "link" as const,
  type: "project" as const,
  title: "React Performance Blog",
  description: "Deep dive into React rendering",
  url: "https://example.com/perf",
  skills: ["React", "TypeScript"],
  tools: ["Chrome DevTools"],
  tags: ["frontend"],
  createdAt: Date.now(),
  updatedAt: Date.now(),
};

const ev2 = {
  id: "ev2",
  userId: "u1",
  applicationId: null,
  kind: "file" as const,
  type: "cert" as const,
  title: "System Design Architecture",
  description: "Distributed cache architecture",
  storageUrl: "https://storage.example.com/file.pdf",
  fileName: "design.pdf",
  skills: ["System Design", "Redis"],
  tools: ["AWS"],
  tags: ["backend"],
  createdAt: Date.now(),
  updatedAt: Date.now(),
};

describe("EvidencePicker", () => {
  it("renders dialog title and search input when open", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1]}
        onPick={vi.fn()}
      />
    );

    expect(screen.getByText("Select evidence")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search by skill, tool, tag, title…")).toBeInTheDocument();
  });

  it("renders all evidence items when no search query", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1, ev2]}
        onPick={vi.fn()}
      />
    );

    expect(screen.getByText("React Performance Blog")).toBeInTheDocument();
    expect(screen.getByText("System Design Architecture")).toBeInTheDocument();
  });

  it("filters evidence items by title search", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1, ev2]}
        onPick={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText("Search by skill, tool, tag, title…");
    fireEvent.change(searchInput, { target: { value: "react" } });

    expect(screen.getByText("React Performance Blog")).toBeInTheDocument();
    expect(screen.queryByText("System Design Architecture")).not.toBeInTheDocument();
  });

  it("filters evidence items by skill search", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1, ev2]}
        onPick={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText("Search by skill, tool, tag, title…");
    fireEvent.change(searchInput, { target: { value: "redis" } });

    expect(screen.queryByText("React Performance Blog")).not.toBeInTheDocument();
    expect(screen.getByText("System Design Architecture")).toBeInTheDocument();
  });

  it("calls onPick with the selected evidence when Use button is clicked", () => {
    const onPick = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <EvidencePicker
        open={true}
        onOpenChange={onOpenChange}
        evidence={[ev1]}
        onPick={onPick}
      />
    );

    // Find and click the "Use" button for ev1
    const useButton = screen.getByRole("button", { name: /use/i });
    fireEvent.click(useButton);

    expect(onPick).toHaveBeenCalledWith(ev1);
  });

  it("closes the dialog after picking evidence", () => {
    const onPick = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <EvidencePicker
        open={true}
        onOpenChange={onOpenChange}
        evidence={[ev1]}
        onPick={onPick}
      />
    );

    const useButton = screen.getByRole("button", { name: /use/i });
    fireEvent.click(useButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows empty state when search returns no matches", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1, ev2]}
        onPick={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText("Search by skill, tool, tag, title…");
    fireEvent.change(searchInput, { target: { value: "zzznomatch" } });

    expect(screen.getByText("No matches.")).toBeInTheDocument();
    expect(screen.getByText(/Try searching by a missing keyword/)).toBeInTheDocument();
  });

  it("renders empty state and no items when evidence list is empty", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[]}
        onPick={vi.fn()}
      />
    );

    expect(screen.getByText("No matches.")).toBeInTheDocument();
  });

  it("shows skill and tool badges on evidence item", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1]}
        onPick={vi.fn()}
      />
    );

    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("TypeScript")).toBeInTheDocument();
    expect(screen.getByText("Chrome DevTools")).toBeInTheDocument();
  });

  it("does not render dialog content when closed", () => {
    render(
      <EvidencePicker
        open={false}
        onOpenChange={vi.fn()}
        evidence={[ev1]}
        onPick={vi.fn()}
      />
    );

    expect(screen.queryByText("Select evidence")).not.toBeInTheDocument();
    expect(screen.queryByText("React Performance Blog")).not.toBeInTheDocument();
  });

  it("handles case-insensitive search", () => {
    render(
      <EvidencePicker
        open={true}
        onOpenChange={vi.fn()}
        evidence={[ev1, ev2]}
        onPick={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText("Search by skill, tool, tag, title…");
    fireEvent.change(searchInput, { target: { value: "REACT" } });

    expect(screen.getByText("React Performance Blog")).toBeInTheDocument();
    expect(screen.queryByText("System Design Architecture")).not.toBeInTheDocument();
  });
});
