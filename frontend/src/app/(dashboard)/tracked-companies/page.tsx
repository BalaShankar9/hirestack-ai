"use client";

/**
 * B2.frontend — Tracked Companies (a.k.a. "Portals to watch").
 *
 * UI for the watchlist that the B1.next portal_scanner_worker reads
 * from. Users add companies they want to monitor across one of six
 * ATS portals (greenhouse / lever / ashby / workday / workable /
 * smartrecruiters); the worker then fetches new postings from those
 * portals on its scheduled cycle and surfaces them in the user's
 * Drafts pane.
 *
 * Design choices:
 *   - Inline form (not a modal) — adding companies should feel like
 *     pasting URLs in /dashboard/batch, not a multi-step wizard.
 *   - Workday is a sub-form: when the provider toggle is `workday`
 *     the tenant input materializes; for the other 5 providers the
 *     row is provider+slug+display_name only.
 *   - 422 responses carry `{ field, reason }` (verified by the
 *     B2.api tests); we surface `reason` directly so the user sees
 *     "company_slug must be lowercase letters, digits, and hyphens"
 *     instead of a generic error.
 *   - 409 (already tracking) and 422 share the same `field` shape
 *     so error rendering is one code path.
 *   - Per-row toggle (enabled) flips via PATCH so the user can
 *     pause without losing the row's history (last_scanned_at).
 *   - Per-row delete uses the existing ConfirmDialog primitive.
 *
 * What this page does NOT do (deferred):
 *   - Batch import via paste (out of scope for B2; could be a
 *     follow-up after we see real usage patterns).
 *   - Surface last_scanned_at — the field exists in the schema but
 *     is owned by the worker (B1.next), and we don't need to render
 *     it until the worker actually starts updating it.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  AlertTriangle,
  Building2,
  Loader2,
  Pause,
  Play,
  Plus,
  Trash2,
} from "lucide-react";

// ── Types (mirror backend serializers) ─────────────────────────────

type Provider =
  | "greenhouse"
  | "lever"
  | "ashby"
  | "workday"
  | "workable"
  | "smartrecruiters";

const PROVIDERS: readonly Provider[] = [
  "greenhouse",
  "lever",
  "ashby",
  "workday",
  "workable",
  "smartrecruiters",
] as const;

const PROVIDER_LABEL: Record<Provider, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  workable: "Workable",
  smartrecruiters: "SmartRecruiters",
};

type TrackedCompany = {
  id: string;
  user_id: string;
  org_id: string | null;
  provider: Provider;
  company_slug: string;
  display_name: string;
  workday_tenant: string | null;
  careers_url: string | null;
  enabled: boolean;
  last_scanned_at: string | null;
  created_at: string;
  updated_at: string;
};

type ListResponse = { items: TrackedCompany[]; count: number };

// ── Helpers ────────────────────────────────────────────────────────

/**
 * Pulls a `{ field, reason }` shape out of the error message thrown
 * by APIClient.request. The backend returns 422 with that detail
 * shape directly; APIClient surfaces it as a thrown Error whose
 * `.message` carries either the JSON-stringified detail or a plain
 * string. Best-effort parser — falls back to the raw message.
 */
function parseFieldError(
  err: unknown,
): { field?: string; reason?: string; raw: string } {
  const raw = err instanceof Error ? err.message : String(err ?? "Unknown error");
  // Try to find a JSON object in the message.
  const match = raw.match(/\{[^{}]*"field"[^{}]*\}/);
  if (match) {
    try {
      const parsed = JSON.parse(match[0]);
      if (parsed && typeof parsed === "object") {
        return {
          field: typeof parsed.field === "string" ? parsed.field : undefined,
          reason: typeof parsed.reason === "string" ? parsed.reason : undefined,
          raw,
        };
      }
    } catch {
      // fall through
    }
  }
  return { raw };
}

// ── Page ───────────────────────────────────────────────────────────

export default function TrackedCompaniesPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<TrackedCompany[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  // Add-form state
  const [provider, setProvider] = useState<Provider>("greenhouse");
  const [companySlug, setCompanySlug] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [workdayTenant, setWorkdayTenant] = useState("");
  const [careersUrl, setCareersUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<{ field?: string; reason?: string; raw: string } | null>(null);

  // Per-row mutation state (id → busy?)
  const [rowBusy, setRowBusy] = useState<Record<string, boolean>>({});
  const [confirmDelete, setConfirmDelete] = useState<TrackedCompany | null>(null);

  const setToken = () => {
    if (session?.access_token) api.setToken(session.access_token);
  };

  async function refresh() {
    setLoading(true);
    setLoadErr(null);
    try {
      setToken();
      const res = (await api.trackedCompanies.list()) as ListResponse;
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setLoadErr(e?.message ?? "Failed to load tracked companies");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (session?.access_token) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token]);

  function resetForm() {
    setCompanySlug("");
    setDisplayName("");
    setWorkdayTenant("");
    setCareersUrl("");
    setCreateErr(null);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateErr(null);
    setCreating(true);
    try {
      setToken();
      const payload: Parameters<typeof api.trackedCompanies.create>[0] = {
        provider,
        company_slug: companySlug.trim(),
        display_name: displayName.trim(),
      };
      if (provider === "workday") {
        payload.workday_tenant = workdayTenant.trim();
      }
      if (careersUrl.trim().length > 0) {
        payload.careers_url = careersUrl.trim();
      }
      const created = (await api.trackedCompanies.create(payload)) as TrackedCompany;
      setItems((cur) => [created, ...cur]);
      resetForm();
    } catch (e: any) {
      setCreateErr(parseFieldError(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(row: TrackedCompany) {
    setRowBusy((b) => ({ ...b, [row.id]: true }));
    try {
      setToken();
      const updated = (await api.trackedCompanies.update(row.id, {
        enabled: !row.enabled,
      })) as TrackedCompany;
      setItems((cur) => cur.map((r) => (r.id === row.id ? updated : r)));
    } catch (e: any) {
      setLoadErr(e?.message ?? "Failed to toggle row");
    } finally {
      setRowBusy((b) => ({ ...b, [row.id]: false }));
    }
  }

  async function handleDelete(row: TrackedCompany) {
    setRowBusy((b) => ({ ...b, [row.id]: true }));
    try {
      setToken();
      await api.trackedCompanies.delete(row.id);
      setItems((cur) => cur.filter((r) => r.id !== row.id));
    } catch (e: any) {
      setLoadErr(e?.message ?? "Failed to delete row");
    } finally {
      setRowBusy((b) => ({ ...b, [row.id]: false }));
      setConfirmDelete(null);
    }
  }

  const enabledCount = useMemo(
    () => items.filter((r) => r.enabled).length,
    [items],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
          Tracked companies
        </h1>
        <p className="text-sm text-slate-600">
          Add companies you want to monitor on their ATS portals.
          We'll surface new postings in your Drafts as they appear.
        </p>
      </header>

      {/* Add form */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-medium text-slate-700">Add a company</h2>
        <form onSubmit={handleCreate} className="mt-3 space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="flex flex-col text-xs font-medium text-slate-700">
              Portal
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
                disabled={creating}
                className="mt-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm"
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_LABEL[p]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col text-xs font-medium text-slate-700 sm:col-span-2">
              Company slug
              <input
                value={companySlug}
                onChange={(e) => setCompanySlug(e.target.value)}
                disabled={creating}
                placeholder="stripe"
                aria-invalid={createErr?.field === "company_slug" || undefined}
                className="mt-1 rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-sm"
              />
              <span className="mt-1 text-[11px] text-slate-500">
                The slug from the portal URL (e.g. <code className="font-mono">stripe</code> in
                {" "}<code className="font-mono">boards.greenhouse.io/stripe</code>).
              </span>
            </label>
          </div>

          <label className="flex flex-col text-xs font-medium text-slate-700">
            Display name
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={creating}
              placeholder="Stripe"
              aria-invalid={createErr?.field === "display_name" || undefined}
              className="mt-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm"
            />
          </label>

          {provider === "workday" && (
            <label className="flex flex-col text-xs font-medium text-slate-700">
              Workday tenant
              <input
                value={workdayTenant}
                onChange={(e) => setWorkdayTenant(e.target.value)}
                disabled={creating}
                placeholder="acme.wd5"
                aria-invalid={createErr?.field === "workday_tenant" || undefined}
                className="mt-1 rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-sm"
              />
              <span className="mt-1 text-[11px] text-slate-500">
                Required for Workday. Found in the careers URL (e.g.{" "}
                <code className="font-mono">acme.wd5</code> in{" "}
                <code className="font-mono">acme.wd5.myworkdayjobs.com</code>).
              </span>
            </label>
          )}

          <label className="flex flex-col text-xs font-medium text-slate-700">
            Careers URL <span className="font-normal text-slate-500">(optional)</span>
            <input
              value={careersUrl}
              onChange={(e) => setCareersUrl(e.target.value)}
              disabled={creating}
              placeholder="https://stripe.com/jobs"
              aria-invalid={createErr?.field === "careers_url" || undefined}
              className="mt-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm"
            />
          </label>

          {createErr && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <strong className="font-semibold">
                  {createErr.field
                    ? `Couldn't add — issue with ${createErr.field}.`
                    : "Couldn't add this company."}
                </strong>{" "}
                {createErr.reason ?? createErr.raw}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={creating || !companySlug.trim() || !displayName.trim()}>
              {creating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Adding…
                </>
              ) : (
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  Add company
                </>
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={resetForm}
              disabled={creating}
            >
              Clear
            </Button>
          </div>
        </form>
      </section>

      {/* List */}
      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-medium text-slate-700">
            Watching{" "}
            <span className="text-slate-500">
              ({enabledCount} active / {items.length} total)
            </span>
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={refresh}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Refresh"
            )}
          </Button>
        </div>

        {loadErr && (
          <div
            role="alert"
            className="border-b border-rose-100 bg-rose-50 px-5 py-2 text-xs text-rose-800"
          >
            {loadErr}
          </div>
        )}

        {!loading && items.length === 0 && !loadErr && (
          <div className="px-5 py-10 text-center text-sm text-slate-500">
            <Building2 className="mx-auto mb-2 h-6 w-6 text-slate-300" />
            No companies yet. Add your first one above.
          </div>
        )}

        <ul className="divide-y divide-slate-100">
          {items.map((row) => (
            <li
              key={row.id}
              className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-slate-900">
                    {row.display_name}
                  </span>
                  <Badge
                    variant="outline"
                    className="text-[11px] uppercase tracking-wide"
                  >
                    {PROVIDER_LABEL[row.provider]}
                  </Badge>
                  {!row.enabled && (
                    <Badge
                      variant="outline"
                      className="border-amber-200 bg-amber-50 text-[11px] text-amber-700"
                    >
                      Paused
                    </Badge>
                  )}
                </div>
                <div className="truncate font-mono text-[11px] text-slate-500">
                  {row.company_slug}
                  {row.workday_tenant ? ` · ${row.workday_tenant}` : ""}
                  {row.careers_url ? ` · ${row.careers_url}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!!rowBusy[row.id]}
                  onClick={() => handleToggle(row)}
                  aria-label={row.enabled ? "Pause" : "Resume"}
                >
                  {rowBusy[row.id] ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : row.enabled ? (
                    <>
                      <Pause className="mr-1.5 h-3.5 w-3.5" />
                      Pause
                    </>
                  ) : (
                    <>
                      <Play className="mr-1.5 h-3.5 w-3.5" />
                      Resume
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="border-rose-200 text-rose-700 hover:bg-rose-50"
                  disabled={!!rowBusy[row.id]}
                  onClick={() => setConfirmDelete(row)}
                  aria-label="Delete"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => {
          if (!open) setConfirmDelete(null);
        }}
        title="Stop tracking this company?"
        description={
          confirmDelete
            ? `We'll stop watching ${confirmDelete.display_name} on ${PROVIDER_LABEL[confirmDelete.provider]}. You can re-add it anytime.`
            : ""
        }
        confirmLabel="Stop tracking"
        variant="destructive"
        onConfirm={() => (confirmDelete ? handleDelete(confirmDelete) : Promise.resolve())}
      />
    </div>
  );
}
