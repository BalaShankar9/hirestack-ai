"use client";

import { memo, useMemo, useState } from "react";
import {
  FileText,
  Download,
  Eye,
  Sparkles,
  ChevronRight,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Search,
  SlidersHorizontal,
  Calendar,
  History,
  Target,
  Bookmark,
  Library,
  FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { DocumentLibraryItem, DocumentCategory } from "@/lib/firestore/models";
import { DocumentUniverseGrid, type DocStatus } from "./document-universe-grid";
import { DOCUMENT_UNIVERSE } from "@/lib/document-universe";

/* ── Helpers ─────────────────────────────────────────────────────── */

/** Canonical display name for a doc type key */
function docTypeLabel(docType: string): string {
  const labels: Record<string, string> = {
    cv: "CV",
    resume: "Résumé",
    cover_letter: "Cover Letter",
    personal_statement: "Personal Statement",
    portfolio: "Portfolio",
    benchmark_cv: "Benchmark CV",
    benchmark_resume: "Benchmark Résumé",
    benchmark_cover_letter: "Benchmark Cover Letter",
    benchmark_personal_statement: "Benchmark Statement",
    benchmark_portfolio: "Benchmark Portfolio",
    scorecard: "ATS Scorecard",
    skills_matrix: "Skills Matrix",
    gap_analysis: "Gap Analysis",
    learning_plan: "Learning Plan",
    career_narrative: "Career Narrative",
    executive_summary: "Executive Summary",
    linkedin_profile: "LinkedIn Profile",
    elevator_pitch: "Elevator Pitch",
    thank_you_letter: "Thank-You Letter",
    reference_sheet: "Reference Sheet",
    project_brief: "Project Brief",
    case_study: "Case Study",
  };
  return labels[docType] || docType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Category metadata */
const CATEGORY_META: Record<DocumentCategory, { label: string; icon: typeof Library; color: string; bg: string }> = {
  tailored:  { label: "Tailored",  icon: Bookmark, color: "text-violet-600", bg: "bg-violet-500/10" },
  benchmark: { label: "Benchmark", icon: Target,   color: "text-amber-600",  bg: "bg-amber-500/10" },
  fixed:     { label: "Fixed",     icon: Library,  color: "text-blue-600",   bg: "bg-blue-500/10" },
};

type SortMode = "type" | "date" | "status";
type FilterCategory = "all" | DocumentCategory;
type FilterStatus = "all" | "ready" | "generating" | "planned" | "error";

/** Group flat docs by docType, keeping newest first within each group */
function groupByType(docs: DocumentLibraryItem[]): { type: string; docs: DocumentLibraryItem[] }[] {
  const map = new Map<string, DocumentLibraryItem[]>();
  for (const d of docs) {
    const arr = map.get(d.docType) || [];
    arr.push(d);
    map.set(d.docType, arr);
  }
  // Sort each group newest-first, then sort groups by latest doc
  const groups: { type: string; docs: DocumentLibraryItem[] }[] = [];
  for (const [type, items] of map) {
    items.sort((a, b) => b.updatedAt - a.updatedAt);
    groups.push({ type, docs: items });
  }
  groups.sort((a, b) => b.docs[0].updatedAt - a.docs[0].updatedAt);
  return groups;
}

function formatDate(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60_000) return "Just now";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
  if (diff < 604800_000) return `${Math.floor(diff / 86400_000)}d ago`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** Rank status for picking the "best" — lower is better */
function statusRank(status: string): number {
  switch (status) {
    case "ready": return 0;
    case "generating": return 1;
    case "planned": return 2;
    case "error": return 3;
    default: return 9;
  }
}

/* ── Status badge ────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "ready":
      return (
        <Badge variant="secondary" className="text-emerald-600 bg-emerald-500/10 border-0 text-[10px] gap-1">
          <CheckCircle2 className="h-3 w-3" /> Ready
        </Badge>
      );
    case "generating":
      return (
        <Badge variant="secondary" className="text-primary bg-primary/10 border-0 text-[10px] gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> Generating
        </Badge>
      );
    case "planned":
      return (
        <Badge variant="secondary" className="text-muted-foreground bg-muted text-[10px] gap-1">
          <Clock className="h-3 w-3" /> Planned
        </Badge>
      );
    case "error":
      return (
        <Badge variant="secondary" className="text-destructive bg-destructive/10 border-0 text-[10px] gap-1">
          <AlertCircle className="h-3 w-3" /> Error
        </Badge>
      );
    default:
      return null;
  }
}

/* ── Category pill ───────────────────────────────────────────────── */

function CategoryPill({ category }: { category: DocumentCategory }) {
  const meta = CATEGORY_META[category];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${meta.bg} ${meta.color}`}>
      {meta.label}
    </span>
  );
}

/* ── Version row (inside a type group) ───────────────────────────── */

interface VersionRowProps {
  doc: DocumentLibraryItem;
  isLatest: boolean;
  onView?: (doc: DocumentLibraryItem) => void;
  onGenerate?: (doc: DocumentLibraryItem) => void;
  onDownload?: (doc: DocumentLibraryItem) => void;
}

const VersionRow = memo(function VersionRow({ doc, isLatest, onView, onGenerate, onDownload }: VersionRowProps) {
  return (
    <div className={`group flex items-center gap-3 rounded-lg px-3 py-2 transition-colors ${
      isLatest ? "bg-muted/40" : "hover:bg-muted/20"
    }`}>
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold ${
        doc.status === "ready"
          ? "bg-emerald-500/10 text-emerald-600"
          : doc.status === "generating"
            ? "bg-primary/10 text-primary"
            : "bg-muted text-muted-foreground"
      }`}>
        v{doc.version}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={doc.status} />
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {formatDate(doc.updatedAt)}
          </span>
          {doc.source && doc.source !== "planner" && (
            <span className="text-[10px] text-muted-foreground/70 capitalize">{doc.source.replace(/_/g, " ")}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {doc.status === "ready" && onView && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onView(doc)}>
            <Eye className="h-3.5 w-3.5" />
          </Button>
        )}
        {doc.status === "ready" && onDownload && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onDownload(doc)}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        )}
        {(doc.status === "planned" || doc.status === "error") && onGenerate && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onGenerate(doc)}>
            <Sparkles className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
});

/* ── Document Type Group ─────────────────────────────────────────── */

interface TypeGroupProps {
  type: string;
  docs: DocumentLibraryItem[];
  onView?: (doc: DocumentLibraryItem) => void;
  onGenerate?: (doc: DocumentLibraryItem) => void;
  onDownload?: (doc: DocumentLibraryItem) => void;
}

const TypeGroup = memo(function TypeGroup({ type, docs, onView, onGenerate, onDownload }: TypeGroupProps) {
  const [expanded, setExpanded] = useState(false);
  const latest = docs[0]; // already sorted newest-first
  const hasVersions = docs.length > 1;
  const readyCount = docs.filter((d) => d.status === "ready").length;

  // Category analysis — show sub-groups when a type spans multiple categories
  const categories = useMemo(() => {
    const seen = new Set<DocumentCategory>();
    for (const d of docs) seen.add(d.docCategory);
    return [...seen];
  }, [docs]);
  const multiCategory = categories.length > 1;

  const categoryGroups = useMemo(() => {
    if (!multiCategory) return null;
    const order: Record<string, number> = { tailored: 0, benchmark: 1, fixed: 2 };
    return [...categories]
      .sort((a, b) => (order[a] ?? 9) - (order[b] ?? 9))
      .map(cat => ({
        category: cat,
        docs: docs.filter(d => d.docCategory === cat),
      }));
  }, [docs, categories, multiCategory]);

  return (
    <div className="rounded-xl border border-border/50 overflow-hidden transition-colors hover:border-border/80">
      {/* Type header — always visible */}
      <div className="flex items-center gap-3 p-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
          latest.status === "ready"
            ? "bg-emerald-500/10"
            : latest.status === "generating"
              ? "bg-primary/10"
              : "bg-muted/50"
        }`}>
          <FileText className={`h-5 w-5 ${
            latest.status === "ready"
              ? "text-emerald-500"
              : latest.status === "generating"
                ? "text-primary"
                : "text-muted-foreground/50"
          }`} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold truncate">{docTypeLabel(type)}</span>
            {categories.map(cat => (
              <CategoryPill key={cat} category={cat} />
            ))}
            <StatusBadge status={latest.status} />
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[11px] text-muted-foreground">
              v{latest.version} · {formatDate(latest.updatedAt)}
            </span>
            {hasVersions && (
              <span className="text-[11px] text-muted-foreground/60">
                · {docs.length} version{docs.length > 1 ? "s" : ""} · {readyCount} ready
              </span>
            )}
          </div>
        </div>

        {/* Actions for latest */}
        <div className="flex items-center gap-1">
          {latest.status === "ready" && onView && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onView(latest)}>
              <Eye className="h-4 w-4" />
            </Button>
          )}
          {latest.status === "ready" && onDownload && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onDownload(latest)}>
              <Download className="h-4 w-4" />
            </Button>
          )}
          {(latest.status === "planned" || latest.status === "error") && onGenerate && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onGenerate(latest)}>
              <Sparkles className="h-4 w-4" />
            </Button>
          )}
          {hasVersions && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-[11px] text-muted-foreground"
              onClick={() => setExpanded(!expanded)}
            >
              <History className="h-3.5 w-3.5" />
              {expanded ? "Hide" : `${docs.length - 1} older`}
              <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""}`} />
            </Button>
          )}
        </div>
      </div>

      {/* Version history — sub-grouped by category when applicable */}
      {expanded && hasVersions && (
        <div className="border-t border-border/30 px-3 pb-3 pt-2 space-y-1">
          {multiCategory && categoryGroups ? (
            categoryGroups.map(({ category, docs: catDocs }) => (
              <div key={category} className="space-y-1">
                <div className="flex items-center gap-2 px-3 pt-1.5 pb-0.5">
                  <CategoryPill category={category} />
                  <span className="text-[10px] text-muted-foreground">
                    {catDocs.length} version{catDocs.length > 1 ? "s" : ""}
                  </span>
                </div>
                {catDocs.map((doc) => (
                  <VersionRow
                    key={doc.id}
                    doc={doc}
                    isLatest={doc.id === latest.id}
                    onView={onView}
                    onGenerate={onGenerate}
                    onDownload={onDownload}
                  />
                ))}
              </div>
            ))
          ) : (
            <>
              <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider px-3 pb-1">
                Version History
              </p>
              {docs.slice(1).map((doc) => (
                <VersionRow
                  key={doc.id}
                  doc={doc}
                  isLatest={false}
                  onView={onView}
                  onGenerate={onGenerate}
                  onDownload={onDownload}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
});

/* ── Filter pill button ──────────────────────────────────────────── */

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "bg-muted/60 text-muted-foreground hover:bg-muted"
      }`}
    >
      {label}
    </button>
  );
}

/* ── Main Document Library View ──────────────────────────────────── */

interface DocumentLibraryViewProps {
  documents: Record<string, DocumentLibraryItem[]>;
  onViewDocument?: (doc: DocumentLibraryItem) => void;
  onGenerateDocument?: (doc: DocumentLibraryItem) => void;
  onDownloadDocument?: (doc: DocumentLibraryItem) => void;
}

export function DocumentLibraryView({
  documents,
  onViewDocument,
  onGenerateDocument,
  onDownloadDocument,
}: DocumentLibraryViewProps) {
  const [search, setSearch] = useState("");
  const [filterCat, setFilterCat] = useState<FilterCategory>("all");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [sortMode, setSortMode] = useState<SortMode>("type");
  const [showFilters, setShowFilters] = useState(false);

  // Flatten all docs from every category
  const allDocs = useMemo(() => Object.values(documents).flat(), [documents]);

  // Apply filters
  const filtered = useMemo(() => {
    let list = allDocs;
    if (filterCat !== "all") list = list.filter((d) => d.docCategory === filterCat);
    if (filterStatus !== "all") list = list.filter((d) => d.status === filterStatus);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (d) =>
          d.label.toLowerCase().includes(q) ||
          d.docType.replace(/_/g, " ").toLowerCase().includes(q) ||
          d.docCategory.toLowerCase().includes(q),
      );
    }
    return list;
  }, [allDocs, filterCat, filterStatus, search]);

  // Group by type and apply sort
  const groups = useMemo(() => {
    const g = groupByType(filtered);
    if (sortMode === "date") {
      g.sort((a, b) => b.docs[0].updatedAt - a.docs[0].updatedAt);
    } else if (sortMode === "status") {
      const statusOrder: Record<string, number> = { generating: 0, error: 1, planned: 2, ready: 3 };
      g.sort((a, b) => (statusOrder[a.docs[0].status] ?? 9) - (statusOrder[b.docs[0].status] ?? 9));
    } else {
      // "type" — alphabetical by label
      g.sort((a, b) => docTypeLabel(a.type).localeCompare(docTypeLabel(b.type)));
    }
    return g;
  }, [filtered, sortMode]);

  // Stats
  const totalDocs = allDocs.length;
  const readyCount = allDocs.filter((d) => d.status === "ready").length;
  const generatingCount = allDocs.filter((d) => d.status === "generating").length;
  const uniqueTypes = new Set(allDocs.map((d) => d.docType)).size;

  return (
    <div className="space-y-5">
      {/* ── Header with stats ── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5 text-primary" />
            <h3 className="text-base font-semibold">Document Library</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            All document types available for this application — browse, generate, and manage.
          </p>
        </div>
        {readyCount > 0 && (
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-0">
              {readyCount} ready
            </Badge>
            {generatingCount > 0 && (
              <Badge variant="secondary" className="text-[10px] bg-primary/10 text-primary border-0 gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                {generatingCount} generating
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* ── Document Universe — primary browsing interface ── */}
      <DocumentUniverseGrid
        title="All Document Types"
        universe={DOCUMENT_UNIVERSE}
        statusMap={(() => {
          const m = new Map<string, DocStatus>();
          for (const doc of allDocs) {
            const existing = m.get(doc.docType);
            // Keep best status: ready > generating > planned > error
            if (!existing || statusRank(doc.status) < statusRank(existing.status)) {
              m.set(doc.docType, {
                status: doc.status as DocStatus["status"],
                version: doc.version,
                updatedAt: doc.updatedAt,
              });
            }
          }
          return m;
        })()}
        onView={(key) => {
          const doc = allDocs.find((d) => d.docType === key && d.status === "ready");
          if (doc && onViewDocument) onViewDocument(doc);
        }}
        onGenerate={(key, label) => {
          // Create a synthetic doc — inherit category from existing doc or default to tailored
          if (onGenerateDocument) {
            const existingDoc = allDocs.find((d) => d.docType === key);
            const category: DocumentCategory = existingDoc?.docCategory ?? "tailored";
            onGenerateDocument({
              id: "",
              userId: "",
              applicationId: "",
              docType: key,
              docCategory: category as DocumentCategory,
              label,
              htmlContent: "",
              metadata: {},
              version: 1,
              status: "planned",
              errorMessage: "",
              source: "user_request",
              createdAt: Date.now(),
              updatedAt: Date.now(),
            });
          }
        }}
        onDownload={(key) => {
          const doc = allDocs.find((d) => d.docType === key && d.status === "ready");
          if (doc && onDownloadDocument) onDownloadDocument(doc);
        }}
      />

      {/* ── Generated Documents — version history & management ── */}
      {totalDocs > 0 && (
        <>
          <Separator />
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <History className="h-4 w-4 text-muted-foreground" />
                  <h4 className="text-sm font-semibold">Generated Documents</h4>
                  <span className="text-[11px] text-muted-foreground">
                    {readyCount}/{totalDocs} ready · {uniqueTypes} type{uniqueTypes !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>
              {/* Search + filter toggle */}
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search documents…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="h-8 w-48 rounded-lg border border-border/60 bg-background pl-8 pr-3 text-xs outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20 transition-colors"
                  />
                </div>
                <Button
                  variant={showFilters ? "secondary" : "ghost"}
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setShowFilters(!showFilters)}
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {/* ── Filter bar ── */}
            {showFilters && (
              <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border/50 p-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Category</span>
                  <div className="flex gap-1">
                    {(["all", "tailored", "benchmark", "fixed"] as FilterCategory[]).map((c) => (
                      <FilterPill key={c} label={c === "all" ? "All" : c.charAt(0).toUpperCase() + c.slice(1)} active={filterCat === c} onClick={() => setFilterCat(c)} />
                    ))}
                  </div>
                </div>
                <div className="h-5 w-px bg-border/60" />
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Status</span>
                  <div className="flex gap-1">
                    {(["all", "ready", "generating", "planned", "error"] as FilterStatus[]).map((s) => (
                      <FilterPill key={s} label={s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)} active={filterStatus === s} onClick={() => setFilterStatus(s)} />
                    ))}
                  </div>
                </div>
                <div className="h-5 w-px bg-border/60" />
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Sort</span>
                  <div className="flex gap-1">
                    {([["type", "Name"], ["date", "Newest"], ["status", "Status"]] as [SortMode, string][]).map(([mode, label]) => (
                      <FilterPill key={mode} label={label} active={sortMode === mode} onClick={() => setSortMode(mode)} />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── Document groups ── */}
            {groups.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <p className="text-xs text-muted-foreground">No matching documents</p>
              </div>
            ) : (
              <div className="space-y-2">
                {groups.map((g) => (
                  <TypeGroup
                    key={g.type}
                    type={g.type}
                    docs={g.docs}
                    onView={onViewDocument}
                    onGenerate={onGenerateDocument}
                    onDownload={onDownloadDocument}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
