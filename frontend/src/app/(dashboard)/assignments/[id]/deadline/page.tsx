"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  in_progress: "In progress",
  done: "Done",
  skipped: "Skipped",
};
const NEXT: Record<string, "in_progress" | "done" | "pending"> = {
  pending: "in_progress",
  in_progress: "done",
  done: "pending",
  skipped: "pending",
};

export default function DeadlineModePage() {
  const { id } = useParams<{ id: string }>();
  const { session } = useAuth();
  const [tasks, setTasks] = useState<any[]>([]);
  const [deadline, setDeadline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    refresh();
  }, [session?.access_token, id]);

  async function refresh() {
    try {
      const [a, t] = await Promise.all([
        api.aim.getAssignment(id).catch(() => null),
        api.aim.listTasks(id),
      ]);
      if (a?.deadline && !deadline) {
        setDeadline(String(a.deadline).slice(0, 10));
      }
      setTasks(t);
    } catch (e: any) {
      setError(e?.message || "Failed to load");
    }
  }

  async function replan() {
    if (!deadline) return;
    setBusy(true);
    setError(null);
    try {
      setTasks(await api.aim.replanTasks(id, deadline));
    } catch (e: any) {
      setError(e?.message || "Replan failed");
    } finally {
      setBusy(false);
    }
  }

  async function cycle(task: any) {
    const next = NEXT[task.status] || "pending";
    try {
      const updated = await api.aim.updateTaskStatus(task.id, next);
      setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, ...updated } : t)));
    } catch (e: any) {
      setError(e?.message || "Update failed");
    }
  }

  const completed = tasks.filter((t) => t.status === "done").length;
  const total = tasks.length;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <Link href={`/assignments/${id}`} className="text-sm text-gray-500 hover:underline">
          ← Assignment
        </Link>
        <h1 className="mt-1 text-3xl font-bold">⏱ Deadline mode</h1>
        <p className="text-sm text-gray-600">
          Backed-off plan from your submission date. {total > 0 && `${completed}/${total} complete.`}
        </p>
      </header>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="flex items-end gap-3 rounded-xl border bg-white p-4">
        <label className="text-sm">
          <span className="block text-gray-600">Deadline (YYYY-MM-DD)</span>
          <input
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </label>
        <button
          onClick={replan}
          disabled={busy || !deadline}
          className="rounded bg-black px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? "Planning…" : tasks.length ? "Re-plan" : "Generate plan"}
        </button>
      </section>

      <section className="rounded-xl border bg-white">
        {tasks.length === 0 ? (
          <p className="p-6 text-sm text-gray-500">
            No plan yet. Set a deadline above and generate one.
          </p>
        ) : (
          <ul className="divide-y">
            {tasks.map((t) => (
              <li
                key={t.id}
                className={`flex items-center justify-between gap-3 p-4 ${
                  t.status === "done" ? "opacity-60" : ""
                }`}
              >
                <button
                  onClick={() => cycle(t)}
                  className="flex-shrink-0 rounded border px-2 py-1 text-xs"
                  title="Click to cycle status"
                >
                  {STATUS_LABELS[t.status] || t.status}
                </button>
                <div className="flex-1">
                  <p
                    className={`font-medium ${
                      t.status === "done" ? "line-through text-gray-500" : ""
                    }`}
                  >
                    {t.task_name}
                  </p>
                  {t.description && (
                    <p className="text-xs text-gray-600">{t.description}</p>
                  )}
                </div>
                <div className="text-right text-xs text-gray-500">
                  <div>{t.due_date}</div>
                  {t.effort_minutes && <div>~{t.effort_minutes} min</div>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
