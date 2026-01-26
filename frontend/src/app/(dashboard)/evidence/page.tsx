"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileUp,
  Link2,
  Plus,
  Search,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { getDownloadURL, ref, uploadBytes } from "firebase/storage";

import { useAuth } from "@/components/providers";
import { storage } from "@/lib/firebase";
import { useApplications, useEvidence } from "@/lib/firestore";
import { createEvidence } from "@/lib/firestore";
import type { EvidenceDoc, EvidenceKind } from "@/lib/firestore";

import { EvidenceCard } from "@/components/workspace/evidence-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

function parseTags(value: string) {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 24);
}

export default function EvidenceVaultPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { data: evidence, loading: evidenceLoading } = useEvidence(user?.uid || null, 300);
  const { data: apps } = useApplications(user?.uid || null, 50);

  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<EvidenceKind>("link");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [skills, setSkills] = useState("");
  const [tools, setTools] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const [pickOpen, setPickOpen] = useState(false);
  const [pendingUse, setPendingUse] = useState<EvidenceDoc | null>(null);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return evidence;
    return evidence.filter((e) => {
      const hay = `${e.title} ${e.description || ""} ${e.skills.join(" ")} ${e.tools.join(" ")} ${e.tags.join(" ")}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [evidence, q]);

  const suggested = useMemo(() => {
    const missing = new Map<string, number>();
    for (const a of apps) {
      if (a.status !== "active") continue;
      for (const kw of a.gaps?.missingKeywords || []) {
        missing.set(kw, (missing.get(kw) || 0) + 1);
      }
    }
    const already = new Set(
      evidence.flatMap((e) => [...e.skills, ...e.tools, ...e.tags].map((x) => x.toLowerCase()))
    );
    return Array.from(missing.entries())
      .filter(([kw]) => !already.has(kw.toLowerCase()))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([kw, count]) => ({ kw, count }));
  }, [apps, evidence]);

  const workspaceTargets = useMemo(() => {
    const active = apps.filter((a) => a.status === "active");
    const rest = apps.filter((a) => a.status !== "active" && a.status !== "archived");
    return [...active, ...rest].slice(0, 12);
  }, [apps]);

  const startUse = (e: EvidenceDoc) => {
    setPendingUse(e);
    setPickOpen(true);
  };

  const useInWorkspace = (appId: string) => {
    if (!pendingUse) return;
    const qs = new URLSearchParams();
    qs.set("tab", "cv");
    qs.set("insertEvidence", pendingUse.id);
    qs.set("insertTarget", "cv");
    setPickOpen(false);
    setPendingUse(null);
    router.push(`/applications/${appId}?${qs.toString()}`);
  };

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setUrl("");
    setSkills("");
    setTools("");
    setTags("");
    setFile(null);
  };

  const onCreate = async () => {
    if (!user) return;
    if (!title.trim()) return;
    if (kind === "link" && !url.trim()) return;
    if (kind === "file" && !file) return;

    setBusy(true);
    try {
      let storagePath: string | undefined;
      let storageUrl: string | undefined;
      let mimeType: string | undefined;

      if (kind === "file" && file) {
        const id = `${Date.now()}_${file.name}`.replace(/\s+/g, "_");
        storagePath = `users/${user.uid}/evidence/${id}`;
        mimeType = file.type || "application/octet-stream";
        const sref = ref(storage, storagePath);
        await uploadBytes(sref, file);
        storageUrl = await getDownloadURL(sref);
      }

      await createEvidence(user.uid, {
        kind,
        title: title.trim(),
        description: description.trim() || undefined,
        url: kind === "link" ? url.trim() : undefined,
        storagePath,
        storageUrl,
        mimeType,
        skills: parseTags(skills),
        tools: parseTags(tools),
        tags: parseTags(tags),
      });

      setOpen(false);
      resetForm();
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border bg-white p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <div className="text-sm font-semibold">Evidence Vault</div>
            <div className="mt-1 text-xs text-muted-foreground leading-relaxed">
              Proof beats claims. Store links/files, tag them by skills/tools, and insert them into your CV with one click.
            </div>
          </div>
          <Button className="gap-2" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            Add evidence
          </Button>
        </div>

        <Separator className="my-4" />

        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by title, skill, tool, tag…"
              className="w-full md:w-[420px]"
            />
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="border tabular-nums">
              {evidence.length} items
            </Badge>
            <Button variant="outline" size="sm" onClick={() => router.push("/new")}>
              Start new application <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="links">Links</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
          <TabsTrigger value="suggested">Suggested</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-4">
          <EvidenceGrid
            loading={evidenceLoading}
            items={filtered}
            onUse={startUse}
          />
        </TabsContent>

        <TabsContent value="links" className="mt-4">
          <EvidenceGrid
            loading={evidenceLoading}
            items={filtered.filter((e) => e.kind === "link")}
            onUse={startUse}
          />
        </TabsContent>

        <TabsContent value="files" className="mt-4">
          <EvidenceGrid
            loading={evidenceLoading}
            items={filtered.filter((e) => e.kind === "file")}
            onUse={startUse}
          />
        </TabsContent>

        <TabsContent value="suggested" className="mt-4">
          <div className="rounded-2xl border bg-white p-5">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-600" />
              <div className="text-sm font-semibold">Suggested evidence to collect</div>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Based on missing keywords across your active applications. Collect proof items to unlock stronger bullets.
            </div>
            <Separator className="my-4" />
            {suggested.length === 0 ? (
              <div className="rounded-xl bg-muted/40 p-4">
                <div className="text-sm font-medium">Nothing suggested right now.</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Generate gaps inside a workspace to get suggestions here.
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {suggested.map((s) => (
                  <Badge key={s.kw} variant="secondary" className="border bg-amber-50 text-amber-900 border-amber-200">
                    {s.kw} <span className="ml-1 opacity-70">({s.count})</span>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      <Dialog
        open={pickOpen}
        onOpenChange={(v) => {
          setPickOpen(v);
          if (!v) setPendingUse(null);
        }}
      >
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Use evidence in a workspace</DialogTitle>
          </DialogHeader>
          <div className="text-xs text-muted-foreground">
            We’ll insert a proof bullet into your Tailored CV where your cursor is.
          </div>

          <Separator className="my-2" />

          {workspaceTargets.length === 0 ? (
            <div className="rounded-xl bg-muted/40 p-4">
              <div className="text-sm font-medium">No workspaces yet.</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Create an application workspace first, then insert evidence into the CV editor.
              </div>
              <div className="mt-4">
                <Button onClick={() => router.push("/new")}>Start the wizard</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {workspaceTargets.map((a) => (
                <button
                  key={a.id}
                  className="w-full rounded-xl border bg-white p-3 text-left hover:bg-muted/40 transition-colors"
                  onClick={() => useInWorkspace(a.id)}
                >
                  <div className="text-sm font-semibold truncate">
                    {a.job.title || "Untitled application"}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground truncate">
                    {a.job.company || "Workspace"} · {a.status === "active" ? "Active" : "Draft"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) resetForm(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add evidence</DialogTitle>
          </DialogHeader>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="rounded-xl border p-3 flex items-start gap-3 cursor-pointer hover:bg-muted/40">
              <input
                type="radio"
                name="kind"
                checked={kind === "link"}
                onChange={() => setKind("link")}
                className="mt-1"
              />
              <div className="min-w-0">
                <div className="text-sm font-semibold flex items-center gap-2">
                  <Link2 className="h-4 w-4 text-blue-600" /> Link
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  PRs, repos, demos, case studies, docs.
                </div>
              </div>
            </label>
            <label className="rounded-xl border p-3 flex items-start gap-3 cursor-pointer hover:bg-muted/40">
              <input
                type="radio"
                name="kind"
                checked={kind === "file"}
                onChange={() => setKind("file")}
                className="mt-1"
              />
              <div className="min-w-0">
                <div className="text-sm font-semibold flex items-center gap-2">
                  <FileUp className="h-4 w-4 text-purple-600" /> File
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  PDFs, screenshots, docs — anything you can attach.
                </div>
              </div>
            </label>
          </div>

          <Separator />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-3">
              <Field label="Title *">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g., CI pipeline speedup PR" />
              </Field>
              <Field label="Description">
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="h-24" placeholder="What does this prove? Add metric + context." />
              </Field>
              {kind === "link" ? (
                <Field label="URL *">
                  <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
                </Field>
              ) : (
                <Field label="File *">
                  <Input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
                </Field>
              )}
            </div>

            <div className="space-y-3">
              <Field label="Skills (comma)">
                <Input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="React, SQL, Docker…" />
              </Field>
              <Field label="Tools (comma)">
                <Input value={tools} onChange={(e) => setTools(e.target.value)} placeholder="Firebase, GCP, Kubernetes…" />
              </Field>
              <Field label="Tags (comma)">
                <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="impact, performance, reliability…" />
              </Field>
              <div className="rounded-xl bg-blue-50 p-3 text-xs text-blue-900/80">
                Coach tip: use tags like <span className="font-semibold">metric</span>,{" "}
                <span className="font-semibold">scope</span>,{" "}
                <span className="font-semibold">constraint</span>. Evidence is only strong when the story is clear.
              </div>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={onCreate} disabled={busy}>
              Add evidence
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EvidenceGrid({
  loading,
  items,
  onUse,
}: {
  loading: boolean;
  items: EvidenceDoc[];
  onUse: (e: EvidenceDoc) => void;
}) {
  if (loading) {
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-2xl border bg-white p-4">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="mt-2 h-4 w-1/2" />
            <Skeleton className="mt-4 h-10 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <div className="text-sm font-semibold">No evidence yet.</div>
        <div className="mt-1 text-xs text-muted-foreground">
          Add links/files and tag them. Then insert proof bullets into your CV from a workspace.
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {items.map((e) => (
        <EvidenceCard
          key={e.id}
          evidence={e}
          onUse={() => onUse(e)}
        />
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground mb-1">{label}</div>
      {children}
    </div>
  );
}
