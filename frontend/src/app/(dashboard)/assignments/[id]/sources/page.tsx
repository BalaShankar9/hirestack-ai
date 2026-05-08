"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Library, Loader2, Plus, Search, Trash2 } from "lucide-react";

import { useAuth } from "@/hooks/use-auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import {
  AIM_RELIABILITY_LABELS,
  AIM_SOURCE_TYPES,
  AIM_VERIFICATION_LABELS,
  type AIMReliabilityTier,
  type AIMSource,
  type AIMSourceType,
  type AIMVerificationStatus,
  missingSourceMetadata,
  sourceTypeLabel,
  splitAuthors,
} from "@/lib/aim";
import { cn } from "@/lib/utils";

const RELIABILITY_BADGE: Record<AIMReliabilityTier, string> = {
  tier_1: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700",
  tier_2: "border-sky-500/20 bg-sky-500/10 text-sky-700",
  tier_3: "border-amber-500/20 bg-amber-500/10 text-amber-700",
  tier_4: "border-slate-500/20 bg-slate-500/10 text-slate-700",
  blocked: "border-rose-500/20 bg-rose-500/10 text-rose-700",
};

const STATUS_BADGE: Record<AIMVerificationStatus, string> = {
  verified: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700",
  unverified: "border-amber-500/20 bg-amber-500/10 text-amber-700",
  needs_metadata: "border-slate-500/20 bg-slate-500/10 text-slate-700",
  blocked: "border-rose-500/20 bg-rose-500/10 text-rose-700",
};

type Assignment = {
  id: string;
  title: string;
  course?: string | null;
  referencing_style?: string | null;
};

type SourceForm = {
  source_type: AIMSourceType;
  title: string;
  authors: string;
  year: string;
  publisher: string;
  journal: string;
  doi: string;
  url: string;
  raw_text: string;
};

const EMPTY_FORM: SourceForm = {
  source_type: "journal_article",
  title: "",
  authors: "",
  year: "",
  publisher: "",
  journal: "",
  doi: "",
  url: "",
  raw_text: "",
};

export default function AssignmentSourcesPage() {
  const params = useParams<{ id: string }>();
  const assignmentId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const { session } = useAuth();
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [sources, setSources] = useState<AIMSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [tierFilter, setTierFilter] = useState<"all" | AIMReliabilityTier>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | AIMVerificationStatus>("all");
  const [form, setForm] = useState<SourceForm>(EMPTY_FORM);

  useEffect(() => {
    if (!session?.access_token || !assignmentId) return;
    api.setToken(session.access_token);
    refresh().finally(() => setLoading(false));
  }, [session?.access_token, assignmentId]);

  async function refresh() {
    if (!assignmentId) return;
    setError(null);
    try {
      const [assignmentRow, sourceRows] = await Promise.all([
        api.aim.getAssignment(assignmentId),
        api.aim.listSources(assignmentId),
      ]);
      setAssignment(assignmentRow as Assignment);
      setSources(Array.isArray(sourceRows) ? sourceRows : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sources");
    }
  }

  async function createSource(event: React.FormEvent) {
    event.preventDefault();
    if (!assignmentId || !form.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.aim.createSource(assignmentId, {
        source_type: form.source_type,
        title: form.title.trim(),
        authors: splitAuthors(form.authors),
        year: form.year ? Number(form.year) : null,
        publisher: form.publisher.trim() || null,
        journal: form.journal.trim() || null,
        doi: form.doi.trim() || null,
        url: form.url.trim() || null,
        raw_text: form.raw_text.trim() || null,
      });
      setSources((current) => [created, ...current]);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add source");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSource(sourceId: string) {
    setDeletingId(sourceId);
    setError(null);
    try {
      await api.aim.deleteSource(sourceId);
      setSources((current) => current.filter((source) => source.id !== sourceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete source");
    } finally {
      setDeletingId(null);
    }
  }

  const summary = useMemo(() => {
    return {
      total: sources.length,
      tier1: sources.filter((source) => source.reliability_tier === "tier_1").length,
      needsMetadata: sources.filter((source) => source.verification_status === "needs_metadata").length,
      blocked: sources.filter((source) => source.verification_status === "blocked" || source.reliability_tier === "blocked").length,
    };
  }, [sources]);

  const filteredSources = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return sources.filter((source) => {
      if (tierFilter !== "all" && source.reliability_tier !== tierFilter) return false;
      if (statusFilter !== "all" && source.verification_status !== statusFilter) return false;
      if (!needle) return true;
      return [
        source.title,
        source.publisher,
        source.journal,
        source.doi,
        source.url,
        source.source_type,
        ...(source.authors || []),
      ].some((value) => String(value || "").toLowerCase().includes(needle));
    });
  }, [query, sources, statusFilter, tierFilter]);

  if (!assignmentId) {
    return <div className="p-6 text-sm text-destructive">Missing assignment id.</div>;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-border/70 bg-card p-6 shadow-soft-sm lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-3">
          <Link href={`/assignments/${assignmentId}`} className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Assignment workspace
          </Link>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Source library</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {assignment?.title || "AIM assignment"}
              {assignment?.course ? ` · ${assignment.course}` : ""}
              {assignment?.referencing_style ? ` · ${assignment.referencing_style}` : ""}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <SourceMetric label="Sources" value={summary.total} />
          <SourceMetric label="Tier 1" value={summary.tier1} />
          <SourceMetric label="Metadata" value={summary.needsMetadata} />
          <SourceMetric label="Blocked" value={summary.blocked} tone={summary.blocked > 0 ? "danger" : "muted"} />
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Card className="h-fit border-border/70">
          <CardHeader>
            <CardTitle className="text-xl">Add source</CardTitle>
            <CardDescription>Attach the source metadata before the writing agent cites it.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={createSource} className="space-y-4">
              <label className="block text-sm font-medium">
                Source type
                <select
                  value={form.source_type}
                  onChange={(event) => setForm((current) => ({ ...current, source_type: event.target.value as AIMSourceType }))}
                  className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                >
                  {AIM_SOURCE_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </label>

              <label className="block text-sm font-medium">
                Title
                <input
                  required
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                  className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Article, report, book, dataset, or page title"
                />
              </label>

              <label className="block text-sm font-medium">
                Authors
                <input
                  value={form.authors}
                  onChange={(event) => setForm((current) => ({ ...current, authors: event.target.value }))}
                  className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Comma-separated authors"
                />
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-medium">
                  Year
                  <input
                    type="number"
                    min={0}
                    max={9999}
                    value={form.year}
                    onChange={(event) => setForm((current) => ({ ...current, year: event.target.value }))}
                    className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>
                <label className="block text-sm font-medium">
                  DOI
                  <input
                    value={form.doi}
                    onChange={(event) => setForm((current) => ({ ...current, doi: event.target.value }))}
                    className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                    placeholder="10.xxxx/..."
                  />
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-medium">
                  Publisher
                  <input
                    value={form.publisher}
                    onChange={(event) => setForm((current) => ({ ...current, publisher: event.target.value }))}
                    className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>
                <label className="block text-sm font-medium">
                  Journal
                  <input
                    value={form.journal}
                    onChange={(event) => setForm((current) => ({ ...current, journal: event.target.value }))}
                    className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>
              </div>

              <label className="block text-sm font-medium">
                URL
                <input
                  type="url"
                  value={form.url}
                  onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))}
                  className="mt-2 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                  placeholder="https://..."
                />
              </label>

              <label className="block text-sm font-medium">
                Source text or note
                <textarea
                  rows={5}
                  value={form.raw_text}
                  onChange={(event) => setForm((current) => ({ ...current, raw_text: event.target.value }))}
                  className="mt-2 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Paste abstract, relevant excerpt, or source note"
                />
              </label>

              <Button type="submit" className="w-full gap-2" loading={saving} disabled={!form.title.trim()}>
                <Plus className="h-4 w-4" />
                Add source
              </Button>
            </form>
          </CardContent>
        </Card>

        <section className="space-y-4">
          <div className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card p-4 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-10 w-full rounded-xl border border-input bg-background pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                placeholder="Search title, author, DOI, URL, or type"
              />
            </div>
            <select
              value={tierFilter}
              onChange={(event) => setTierFilter(event.target.value as "all" | AIMReliabilityTier)}
              className="h-10 rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="all">All tiers</option>
              {Object.entries(AIM_RELIABILITY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as "all" | AIMVerificationStatus)}
              className="h-10 rounded-xl border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="all">All statuses</option>
              {Object.entries(AIM_VERIFICATION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-border/70 bg-card/40">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : sources.length === 0 ? (
            <EmptyState
              icon={Library}
              title="No sources attached"
              description="Add at least one credible source before generating citation-backed assignment sections."
              variant="dashed"
            />
          ) : filteredSources.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matching sources"
              description="Adjust the filters or search terms to bring sources back into view."
              variant="dashed"
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {filteredSources.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  deleting={deletingId === source.id}
                  onDelete={() => deleteSource(source.id)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function SourceMetric({ label, value, tone = "muted" }: { label: string; value: number; tone?: "muted" | "danger" }) {
  return (
    <div className={cn("rounded-xl border px-3 py-2", tone === "danger" ? "border-rose-500/20 bg-rose-500/5" : "bg-muted/30")}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function SourceCard({ source, deleting, onDelete }: { source: AIMSource; deleting: boolean; onDelete: () => void }) {
  const missing = missingSourceMetadata(source);
  const title = source.title || "Untitled source";
  const authors = source.authors?.length ? source.authors.join(", ") : "No author";
  return (
    <Card className="border-border/70 hover:shadow-soft-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={RELIABILITY_BADGE[source.reliability_tier]}>
            {AIM_RELIABILITY_LABELS[source.reliability_tier]}
          </Badge>
          <Badge variant="outline" className={STATUS_BADGE[source.verification_status]}>
            {AIM_VERIFICATION_LABELS[source.verification_status]}
          </Badge>
          <Badge variant="outline">{sourceTypeLabel(source.source_type)}</Badge>
        </div>
        <CardTitle className="text-lg leading-snug">{title}</CardTitle>
        <CardDescription>{authors}{source.year ? ` · ${source.year}` : ""}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="space-y-1 text-muted-foreground">
          {source.journal && <div>Journal: {source.journal}</div>}
          {source.publisher && <div>Publisher: {source.publisher}</div>}
          {source.doi && <div>DOI: {source.doi}</div>}
          {source.url && (
            <a href={source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
              Open source <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
        {source.extracted_summary && (
          <p className="rounded-xl bg-muted/30 p-3 text-muted-foreground">{source.extracted_summary}</p>
        )}
        {missing.length > 0 && (
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-800">
            Missing: {missing.join(", ")}
          </div>
        )}
        <div className="flex justify-end">
          <Button type="button" variant="ghost" size="sm" onClick={onDelete} loading={deleting} className="gap-2 text-destructive hover:text-destructive">
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}