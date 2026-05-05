"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";

export default function AssignmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { session } = useAuth();
  const [assignment, setAssignment] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [analysis, setAnalysis] = useState<any | null>(null);
  const [sections, setSections] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Brief / rubric paste form
  const [docType, setDocType] = useState<"brief" | "rubric">("brief");
  const [docText, setDocText] = useState("");
  const [docFile, setDocFile] = useState<File | null>(null);

  useEffect(() => {
    if (!session?.access_token || !id) return;
    api.setToken(session.access_token);
    refresh();
  }, [session?.access_token, id]);

  async function refresh() {
    try {
      const [a, d, secs] = await Promise.all([
        api.aim.getAssignment(id),
        api.aim.listDocuments(id),
        api.aim.listSections(id).catch(() => []),
      ]);
      setAssignment(a);
      setDocs(d);
      setSections(secs);
      try {
        setAnalysis(await api.aim.getAnalysis(id));
      } catch {
        setAnalysis(null);
      }
      try {
        setEvaluations(await api.aim.listEvaluations(id));
      } catch {
        setEvaluations([]);
      }
      try {
        setTasks(await api.aim.listTasks(id));
      } catch {
        setTasks([]);
      }
    } catch (e: any) {
      setError(e?.message || "Failed to load");
    }
  }

  async function attachDoc() {
    if (!docText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.aim.attachDocumentText(id, { type: docType, raw_text: docText });
      setDocText("");
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Failed to attach");
    } finally {
      setBusy(false);
    }
  }

  async function uploadDoc() {
    if (!docFile) return;
    setBusy(true);
    setError(null);
    try {
      await api.aim.uploadDocument(id, docFile, docType);
      setDocFile(null);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function runAnalyze() {
    setBusy(true);
    setError(null);
    try {
      await api.aim.analyze(id);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  async function runPredict() {
    setBusy(true);
    setError(null);
    try {
      await api.aim.predictGrade(id);
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Prediction failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAssignment() {
    if (!confirm("Delete this assignment and all its sections?")) return;
    await api.aim.deleteAssignment(id);
    router.push("/assignments");
  }

  if (!assignment) return <div className="p-6">Loading…</div>;
  const latestEval = evaluations[0];

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6">
      <header className="flex items-start justify-between">
        <div>
          <Link href="/assignments" className="text-sm text-gray-500 hover:underline">
            ← All assignments
          </Link>
          <h1 className="mt-1 text-3xl font-bold">{assignment.title}</h1>
          <p className="text-sm text-gray-600">
            {assignment.course} · {assignment.academic_level} · {assignment.referencing_style} ·{" "}
            target {assignment.word_count} words
          </p>
          <span className="mt-2 inline-block rounded bg-gray-100 px-2 py-1 text-xs">
            Status: {assignment.status}
          </span>
        </div>
        <button onClick={deleteAssignment} className="text-sm text-red-600 hover:underline">
          Delete
        </button>
      </header>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="rounded-xl border bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">1 · Brief & rubric</h2>
        <div className="mb-3 flex gap-2">
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as any)}
            className="rounded border px-2 py-1 text-sm"
          >
            <option value="brief">Brief</option>
            <option value="rubric">Rubric</option>
          </select>
          <button
            onClick={attachDoc}
            disabled={busy || !docText.trim()}
            className="rounded bg-black px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
          >
            Attach text
          </button>
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => setDocFile(e.target.files?.[0] || null)}
            className="text-sm"
          />
          <button
            onClick={uploadDoc}
            disabled={busy || !docFile}
            className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          >
            Upload file
          </button>
          <Link
            href={`/assignments/${id}/deadline`}
            className="ml-auto rounded border px-3 py-1 text-sm hover:bg-gray-50"
          >
            ⏱ Deadline mode
            {tasks.length > 0 && (
              <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                {tasks.filter((t) => t.status === "done").length}/{tasks.length}
              </span>
            )}
          </Link>
        </div>
        <textarea
          rows={6}
          placeholder="Paste assignment brief or rubric…"
          className="w-full rounded border p-2 text-sm"
          value={docText}
          onChange={(e) => setDocText(e.target.value)}
        />
        <ul className="mt-3 space-y-1 text-sm">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center gap-2">
              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{d.type}</span>
              <span className="text-gray-700">
                {d.file_name || `${(d.raw_text || "").length} chars`}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border bg-white p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">2 · Plan (Parser + Recon)</h2>
          <button
            onClick={runAnalyze}
            disabled={busy || docs.filter((d) => d.type === "brief").length === 0}
            className="rounded bg-black px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
          >
            {analysis ? "Re-analyze" : "Analyze"}
          </button>
        </div>
        {analysis?.needs_clarification && (
          <div className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-semibold">Clarification needed (parser confidence{" "}
              {(analysis.parser_confidence * 100).toFixed(0)}%):</p>
            <ul className="mt-1 list-disc pl-5">
              {(analysis.clarification_questions || []).map((q: string, i: number) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        )}
        {analysis && !analysis.needs_clarification && (
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold">Directive</h3>
              <p className="text-sm text-gray-700">{analysis.directive || "—"}</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold">Distinction strategy</h3>
              <p className="text-sm text-gray-700">
                {(analysis.expectations?.distinction_strategy as string) || "—"}
              </p>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-xl border bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">3 · Sections</h2>
        {sections.length === 0 ? (
          <p className="text-sm text-gray-500">
            Run analysis to materialize sections from the recon plan.
          </p>
        ) : (
          <ul className="divide-y">
            {sections.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-3">
                <div>
                  <Link
                    href={`/assignments/${id}/sections/${s.id}`}
                    className="font-semibold hover:underline"
                  >
                    {s.order_index + 1}. {s.title}
                  </Link>
                  <div className="text-xs text-gray-500">
                    Target: {s.word_limit || "?"} words
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border bg-white p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">4 · Grade prediction</h2>
          <button
            onClick={runPredict}
            disabled={busy || sections.length === 0}
            className="rounded bg-black px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
          >
            Predict grade
          </button>
        </div>
        {latestEval && (
          <div className="mt-3">
            <p className="text-sm">
              Range: <strong>{latestEval.predicted_grade_low}–{latestEval.predicted_grade_high}</strong>{" "}
              · Band: <strong>{latestEval.band}</strong>
            </p>
            {latestEval.reasoning && (
              <p className="mt-2 text-sm text-gray-700">{latestEval.reasoning}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
