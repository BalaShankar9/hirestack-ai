"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { QualityScoreGauge } from "@/design-system/components/QualityScoreGauge";
import { useAIMStream, type AIMAttempt } from "@/hooks/use-aim-stream";
import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";

export default function SectionWorkbench() {
  const { id, sectionId } = useParams<{ id: string; sectionId: string }>();
  const { session } = useAuth();
  const stream = useAIMStream();
  const [section, setSection] = useState<any>(null);
  const [outputs, setOutputs] = useState<any[]>([]);
  const [fixDraft, setFixDraft] = useState("");
  const [fixResult, setFixResult] = useState<any | null>(null);
  const [fixBusy, setFixBusy] = useState(false);

  useEffect(() => {
    if (!session?.access_token) return;
    api.setToken(session.access_token);
    refresh();
  }, [session?.access_token, sectionId]);

  async function refresh() {
    const sections = await api.aim.listSections(id);
    setSection(sections.find((s) => s.id === sectionId) || null);
    try {
      setOutputs(await api.aim.listSectionOutputs(sectionId));
    } catch {
      setOutputs([]);
    }
  }

  // After streaming finishes, refetch persisted outputs
  useEffect(() => {
    if (stream.done) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.done]);

  const liveAttempts: AIMAttempt[] = stream.attempts;
  const current = outputs.find((o) => o.is_current) || outputs[0];
  const score = current?.quality_score ?? liveAttempts[liveAttempts.length - 1]?.weighted_score;

  if (!section) return <div className="p-6">Loading…</div>;

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6">
      <header>
        <Link href={`/assignments/${id}`} className="text-sm text-gray-500 hover:underline">
          ← Assignment
        </Link>
        <h1 className="mt-1 text-3xl font-bold">{section.title}</h1>
        <p className="text-sm text-gray-600">
          Target: {section.word_limit || "?"} words · {section.purpose || ""}
        </p>
      </header>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-[auto,1fr]">
        <div>
          <QualityScoreGauge score={score ?? null} />
          <button
            onClick={() => stream.start(sectionId)}
            disabled={stream.isStreaming}
            className="mt-3 w-full rounded bg-black px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {stream.isStreaming ? "Generating…" : current ? "Regenerate" : "Generate section"}
          </button>
          {stream.isStreaming && (
            <button
              onClick={stream.cancel}
              className="mt-2 w-full rounded border px-3 py-2 text-sm"
            >
              Cancel
            </button>
          )}
          {stream.done && (
            <p className="mt-2 text-xs text-gray-600">
              Stop reason: <strong>{stream.stopReason}</strong> ·{" "}
              {stream.passedGate ? "✅ passed gate" : "⚠️ below 85"}
            </p>
          )}
          {stream.error && <p className="mt-2 text-xs text-red-600">{stream.error}</p>}
        </div>

        <div className="space-y-4">
          {liveAttempts.length > 0 ? (
            liveAttempts.map((a) => (
              <article key={a.version} className="rounded-xl border bg-white p-4">
                <header className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold">
                    Attempt {a.version} · {a.weighted_score.toFixed(1)} / 100
                  </span>
                  <span className="text-gray-500">
                    {a.word_count} words · {a.latency_ms}ms
                  </span>
                </header>
                <div className="prose prose-sm max-w-none whitespace-pre-wrap text-gray-800">
                  {a.content}
                </div>
                {a.reviewer?.ranked_issues?.length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs text-gray-600">
                      Reviewer issues ({a.reviewer.ranked_issues.length})
                    </summary>
                    <ul className="mt-1 list-disc pl-5 text-xs text-gray-700">
                      {a.reviewer.ranked_issues.slice(0, 8).map((iss: any, i: number) => (
                        <li key={i}>
                          <strong>[{iss.severity}]</strong> {iss.issue}
                          {iss.suggested_fix && <em> — {iss.suggested_fix}</em>}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </article>
            ))
          ) : current ? (
            <article className="rounded-xl border bg-white p-4">
              <header className="mb-2 flex items-center justify-between text-xs">
                <span className="font-semibold">
                  v{current.version} · {Number(current.quality_score || 0).toFixed(1)} / 100
                </span>
                <span className="text-gray-500">
                  {current.passed_gate ? "✅ passed" : "⚠️ below 85"} · {current.model_used}
                </span>
              </header>
              <div className="prose prose-sm max-w-none whitespace-pre-wrap text-gray-800">
                {current.content}
              </div>
            </article>
          ) : (
            <p className="text-sm text-gray-500">
              No content yet. Click <em>Generate section</em> to start the writer→reviewer loop.
            </p>
          )}
        </div>
      </section>

      {outputs.length > 1 && (
        <section className="rounded-xl border bg-white p-5">
          <h2 className="mb-2 text-lg font-semibold">History</h2>
          <ul className="text-sm">
            {outputs.map((o) => (
              <li key={o.id} className="flex items-center justify-between border-b py-2">
                <span>
                  v{o.version} · {Number(o.quality_score || 0).toFixed(1)} ·{" "}
                  {o.passed_gate ? "passed" : "below"}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(o.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-xl border bg-white p-5">
        <h2 className="mb-2 text-lg font-semibold">Fix-My-Section</h2>
        <p className="mb-3 text-sm text-gray-600">
          Paste your own draft to get a diagnostic critique without overwriting current outputs.
        </p>
        <textarea
          rows={8}
          value={fixDraft}
          onChange={(e) => setFixDraft(e.target.value)}
          placeholder="Paste a draft (your own writing) for diagnostic feedback…"
          className="w-full rounded border p-2 text-sm"
        />
        <button
          onClick={async () => {
            if (!fixDraft.trim()) return;
            setFixBusy(true);
            try {
              setFixResult(await api.aim.fixSection(sectionId, fixDraft));
            } catch (e: any) {
              setFixResult({ error: e?.message || "Fix failed" });
            } finally {
              setFixBusy(false);
            }
          }}
          disabled={fixBusy || !fixDraft.trim()}
          className="mt-2 rounded bg-black px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {fixBusy ? "Analysing…" : "Diagnose draft"}
        </button>
        {fixResult && !fixResult.error && (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              Score: <strong>{Number(fixResult.weighted_score || 0).toFixed(1)}</strong> · Gate:{" "}
              {fixResult.passed_gate ? "✅ passed" : "⚠️ below 85"}
            </p>
            {fixResult.ranked_issues?.length > 0 && (
              <ul className="list-disc pl-5 text-gray-700">
                {fixResult.ranked_issues.slice(0, 8).map((iss: any, i: number) => (
                  <li key={i}>
                    <strong>[{iss.severity}]</strong> {iss.issue}
                    {iss.suggested_fix && <em> — {iss.suggested_fix}</em>}
                  </li>
                ))}
              </ul>
            )}
            {fixResult.revised_draft && (
              <details>
                <summary className="cursor-pointer text-gray-600">View revised draft</summary>
                <div className="mt-2 whitespace-pre-wrap rounded bg-gray-50 p-3">
                  {fixResult.revised_draft}
                </div>
                <button
                  onClick={async () => {
                    if (!confirm("Save revised draft as a new current version?")) return;
                    try {
                      await api.aim.applyManualDraft(
                        sectionId,
                        fixResult.revised_draft,
                        fixResult.weighted_score,
                      );
                      await refresh();
                    } catch (e: any) {
                      setFixResult({ ...fixResult, error: e?.message || "Apply failed" });
                    }
                  }}
                  className="mt-2 rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white"
                >
                  Apply revised draft as new version
                </button>
              </details>
            )}
          </div>
        )}
        {fixResult?.error && <p className="mt-2 text-xs text-red-600">{fixResult.error}</p>}
      </section>
    </div>
  );
}
