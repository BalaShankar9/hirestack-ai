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
        applicationId: "a1",
        source: "gaps",
        title: "Add proof for Firebase",
        priority: "high",
        status: "todo",
        createdAt: Date.now(),
        updatedAt: Date.now(),
      },
      {
        id: "t2",
        userId: "u1",
        appId: "a1",
        applicationId: "a1",
        source: "learningPlan",
        title: "Sprint: strengthen System Design",
        priority: "medium",
        status: "done",
        createdAt: Date.now(),
        updatedAt: Date.now(),
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

