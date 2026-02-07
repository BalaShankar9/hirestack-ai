"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  Upload,
  Link2,
  FileText,
  Trash2,
  ExternalLink,
} from "lucide-react";

import { useAuth } from "@/components/providers";
import { useEvidence } from "@/lib/firestore";
import {
  createEvidence,
  deleteEvidence,
  uploadEvidenceFile,
} from "@/lib/firestore/ops";
import type { EvidenceDoc } from "@/lib/firestore/models";

import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const EVIDENCE_TYPES = [
  { value: "cert", label: "Certification" },
  { value: "project", label: "Project" },
  { value: "course", label: "Course" },
  { value: "award", label: "Award" },
  { value: "publication", label: "Publication" },
  { value: "other", label: "Other" },
] as const;

export default function EvidenceVaultPage() {
  const router = useRouter();
  const { user } = useAuth();

  const { data: evidence, loading } = useEvidence(user?.uid ?? null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Form state
  const [kind, setKind] = useState<"link" | "file">("link");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("other");
  const [url, setUrl] = useState("");
  const [skills, setSkills] = useState("");
  const [tools, setTools] = useState("");
  const [tags, setTags] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function resetForm() {
    setKind("link");
    setTitle("");
    setDescription("");
    setType("other");
    setUrl("");
    setSkills("");
    setTools("");
    setTags("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setUploading(true);

    try {
      let fileUrl: string | undefined;
      let fileName: string | undefined;

      if (kind === "file" && fileRef.current?.files?.[0]) {
        const file = fileRef.current.files[0];
        fileName = file.name;
        fileUrl = await uploadEvidenceFile(user.uid, file);
      }

      await createEvidence(user.uid, {
        userId: user.uid,
        applicationId: null,
        kind,
        type: type as EvidenceDoc["type"],
        title,
        description: description || undefined,
        url: kind === "link" ? url : undefined,
        storageUrl: fileUrl,
        fileUrl,
        fileName,
        skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        tools: tools
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        tags: tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });

      resetForm();
      setDialogOpen(false);
    } catch (err) {
      console.error("Failed to create evidence:", err);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this evidence item?")) return;
    try {
      await deleteEvidence(id);
    } catch (err) {
      console.error("Failed to delete evidence:", err);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Evidence Vault</h1>
          <p className="text-muted-foreground text-sm">
            Collect and organize proof of your skills — certifications, projects, links, and more.
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-xl">
              <Plus className="mr-2 h-4 w-4" />
              Add Evidence
            </Button>
          </DialogTrigger>

          <DialogContent className="max-w-lg rounded-2xl">
            <DialogHeader>
              <DialogTitle>Add Evidence</DialogTitle>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Kind toggle */}
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={kind === "link" ? "default" : "outline"}
                  size="sm"
                  className="rounded-xl"
                  onClick={() => setKind("link")}
                >
                  <Link2 className="mr-1.5 h-4 w-4" />
                  Link
                </Button>
                <Button
                  type="button"
                  variant={kind === "file" ? "default" : "outline"}
                  size="sm"
                  className="rounded-xl"
                  onClick={() => setKind("file")}
                >
                  <Upload className="mr-1.5 h-4 w-4" />
                  File
                </Button>
              </div>

              <div className="space-y-1.5">
                <Label>Title</Label>
                <Input
                  required
                  className="rounded-xl h-11"
                  placeholder="e.g. AWS Solutions Architect cert"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Type</Label>
                <Select value={type} onValueChange={setType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EVIDENCE_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea
                  rows={2}
                  placeholder="What does this prove?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              {kind === "link" ? (
                <div className="space-y-1.5">
                  <Label>URL</Label>
                  <Input
                    type="url"
                    placeholder="https://..."
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                  />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <Label>File</Label>
                  <Input type="file" ref={fileRef} />
                </div>
              )}

              <div className="space-y-1.5">
                <Label>Skills (comma-separated)</Label>
                <Input
                  placeholder="React, TypeScript, Node.js"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Tools (comma-separated)</Label>
                <Input
                  placeholder="Docker, AWS, Figma"
                  value={tools}
                  onChange={(e) => setTools(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Tags (comma-separated)</Label>
                <Input
                  placeholder="frontend, performance, leadership"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                />
              </div>

              <Button type="submit" className="w-full rounded-xl" disabled={uploading}>
                {uploading ? "Uploading…" : "Add Evidence"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {evidence.length === 0 ? (
        <div className="rounded-2xl border border-dashed bg-card/50">
          <div className="flex flex-col items-center justify-center py-12">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
              <FileText className="h-6 w-6 text-primary" />
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              No evidence yet. Click “Add Evidence” to get started.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {evidence.map((ev: EvidenceDoc) => {
            const link = ev.kind === "link" ? ev.url : ev.storageUrl;
            return (
              <div key={ev.id} className="relative group rounded-2xl border bg-card shadow-soft-sm hover:shadow-soft-md transition-shadow overflow-hidden">
                <div className="p-4 pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-semibold truncate">{ev.title}</div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {link && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => window.open(link, "_blank", "noopener")}
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive"
                        onClick={() => handleDelete(ev.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="px-4 pb-4 space-y-2">
                  {ev.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {ev.description}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline" className="text-[10px]">
                      {ev.type}
                    </Badge>
                    {ev.skills.slice(0, 3).map((s: string) => (
                      <Badge key={s} variant="secondary" className="text-[10px]">
                        {s}
                      </Badge>
                    ))}
                    {ev.tools.slice(0, 3).map((t: string) => (
                      <Badge key={t} variant="secondary" className="text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
