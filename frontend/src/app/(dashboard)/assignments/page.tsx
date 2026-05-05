"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";

export default function AssignmentsPage() {
  const { user, session } = useAuth();
  const [assignments, setAssignments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [usage, setUsage] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    course: "",
    academic_level: "ug" as "ug" | "pg" | "mba" | "phd" | "other",
    referencing_style: "harvard" as "harvard" | "apa" | "mla" | "chicago" | "ieee" | "other",
    word_count: 2000,
  });

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    (async () => {
      try {
        const [list, u] = await Promise.all([
          api.aim.listAssignments(),
          api.aim.getUsage(),
        ]);
        setAssignments(list);
        setUsage(u);
      } catch (e: any) {
        setError(e?.message || "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, [session?.access_token]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      const created = await api.aim.createAssignment(form);
      setAssignments((a) => [created, ...a]);
      setForm({ ...form, title: "", course: "" });
      const u = await api.aim.getUsage();
      setUsage(u);
    } catch (e: any) {
      setError(e?.message || "Failed to create");
    } finally {
      setCreating(false);
    }
  };

  if (!user) return <div className="p-6">Please sign in.</div>;
  if (loading) return <div className="p-6">Loading…</div>;

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold">Assignments</h1>
          <p className="text-sm text-gray-600">
            Plan, draft, and grade-predict university assignments with the AIM agent pipeline.
          </p>
        </div>
        {usage && (
          <div className="text-right text-sm">
            <div className="font-semibold">
              {usage.assignments_created} / {usage.free_assignment_limit ?? "∞"} this month
            </div>
            <div className="text-gray-500">Plan: {usage.plan}</div>
          </div>
        )}
      </header>

      <section className="rounded-xl border bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">New assignment</h2>
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input
            required
            placeholder="Title (e.g. PESTLE on Tesla 2025)"
            className="rounded border px-3 py-2"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <input
            placeholder="Course (e.g. MBA Strategy)"
            className="rounded border px-3 py-2"
            value={form.course}
            onChange={(e) => setForm({ ...form, course: e.target.value })}
          />
          <select
            className="rounded border px-3 py-2"
            value={form.academic_level}
            onChange={(e) => setForm({ ...form, academic_level: e.target.value as any })}
          >
            <option value="ug">Undergraduate</option>
            <option value="pg">Postgraduate</option>
            <option value="mba">MBA</option>
            <option value="phd">PhD</option>
            <option value="other">Other</option>
          </select>
          <select
            className="rounded border px-3 py-2"
            value={form.referencing_style}
            onChange={(e) => setForm({ ...form, referencing_style: e.target.value as any })}
          >
            <option value="harvard">Harvard</option>
            <option value="apa">APA</option>
            <option value="mla">MLA</option>
            <option value="chicago">Chicago</option>
            <option value="ieee">IEEE</option>
            <option value="other">Other</option>
          </select>
          <input
            type="number"
            min={500}
            max={20000}
            step={100}
            className="rounded border px-3 py-2"
            value={form.word_count}
            onChange={(e) => setForm({ ...form, word_count: Number(e.target.value) })}
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded bg-black px-4 py-2 font-semibold text-white disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create assignment"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Your assignments</h2>
        {assignments.length === 0 && (
          <p className="text-sm text-gray-500">No assignments yet — create one above.</p>
        )}
        <ul className="divide-y rounded-xl border bg-white">
          {assignments.map((a) => (
            <li key={a.id} className="flex items-center justify-between p-4">
              <div>
                <Link href={`/assignments/${a.id}`} className="font-semibold hover:underline">
                  {a.title}
                </Link>
                <div className="text-xs text-gray-500">
                  {a.course || "No course"} · {a.academic_level || "level?"} ·{" "}
                  {a.referencing_style || "style?"}
                </div>
              </div>
              <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700">
                {a.status}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
