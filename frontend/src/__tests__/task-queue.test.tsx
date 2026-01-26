import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TaskQueue } from "@/components/workspace/task-queue";
import type { TaskDoc } from "@/lib/firestore";

describe("TaskQueue", () => {
  it("shows todo items by default and toggles filter", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();

    const tasks: TaskDoc[] = [
      {
        id: "t1",
        userId: "u1",
        appId: "a1",
        source: "gaps",
        module: "gaps",
        title: "Add proof for “Firebase”",
        priority: "high",
        status: "todo",
        createdAt: Date.now(),
        tags: ["firebase"],
      },
      {
        id: "t2",
        userId: "u1",
        appId: "a1",
        source: "learningPlan",
        module: "learningPlan",
        title: "Sprint: strengthen System Design",
        priority: "medium",
        status: "done",
        createdAt: Date.now(),
        completedAt: Date.now(),
        tags: ["learning"],
      },
    ];

    render(<TaskQueue tasks={tasks} onToggle={onToggle} compact />);

    expect(screen.getByText(/1 open/i)).toBeInTheDocument();
    expect(screen.getByText(/Add proof for/i)).toBeInTheDocument();
    expect(screen.queryByText(/Sprint: strengthen/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Show all/i }));
    expect(screen.getByText(/Sprint: strengthen/i)).toBeInTheDocument();

    await user.click(screen.getByText(/Add proof for/i));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0][0].id).toBe("t1");
  });
});

