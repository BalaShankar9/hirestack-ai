"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileUp,
  Lock,
  Sparkles,
  Wand2,
} from "lucide-react";
import { getDownloadURL, ref, uploadBytesResumable, type UploadTask } from "firebase/storage";
import { Bytes } from "firebase/firestore";

import { useAuth } from "@/components/providers";
import { storage } from "@/lib/firebase";
import {
  computeJDQuality,
  createApplication,
  extractKeywords,
  generateApplicationModules,
  patchApplication,
  setModuleStatus,
  trackEvent,
} from "@/lib/firestore";
import type { ConfirmedFacts, ModuleKey } from "@/lib/firestore";
import { useApplication, useEvidence } from "@/lib/firestore";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusStepper } from "@/components/workspace/status-stepper";

function PageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { user } = useAuth();

  const urlAppId = search.get("appId");
  const step = Number(search.get("step") || "1");

  const [resolvedAppId, setResolvedAppId] = useState<string | null>(urlAppId);
  const createAppPromiseRef = useRef<Promise<string> | null>(null);
  const resumeOpIdRef = useRef(0);
  const resumeUploadTaskRef = useRef<UploadTask | null>(null);
  const resumeFileRef = useRef<File | null>(null);

  const [busy, setBusy] = useState(false);
  const [resumeUploadInFlight, setResumeUploadInFlight] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      try {
        resumeUploadTaskRef.current?.cancel();
      } catch {}
      resumeUploadTaskRef.current = null;
      resumeOpIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    setResolvedAppId(urlAppId);
  }, [urlAppId]);

  // Keep the URL in sync once we have an app id (but avoid doing this mid-action).
  useEffect(() => {
    if (!resolvedAppId) return;
    if (urlAppId === resolvedAppId) return;
    if (busy) return;
    const qs = new URLSearchParams(search.toString());
    qs.set("appId", resolvedAppId);
    qs.set("step", String(step));
    router.replace(`/new?${qs.toString()}`);
  }, [busy, resolvedAppId, router, search, step, urlAppId]);

  const { data: app } = useApplication(resolvedAppId);
  const { data: evidence } = useEvidence(user?.uid || null, 50);

  const [firestoreReady, setFirestoreReady] = useState<boolean | null>(null);
  const [firestoreStatusError, setFirestoreStatusError] = useState<string | null>(null);
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [storageStatusError, setStorageStatusError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) return;

    (async () => {
      try {
        const res = await fetch(`${apiUrl.replace(/\/$/, "")}/health`, { cache: "no-store" });
        const json = await res.json().catch(() => null);
        const ok = json?.firebase?.firestore?.ok;
        const storageOk = json?.firebase?.storage?.ok;
        if (cancelled) return;

        if (ok === false) {
          setFirestoreReady(false);
          setFirestoreStatusError(json?.firebase?.firestore?.error || "Firestore is not ready.");
        } else if (ok === true) {
          setFirestoreReady(true);
          setFirestoreStatusError(null);
        }

        if (storageOk === false) {
          setStorageReady(false);
          setStorageStatusError(json?.firebase?.storage?.error || "Firebase Storage is not ready.");
        } else if (storageOk === true) {
          setStorageReady(true);
          setStorageStatusError(null);
        }
      } catch {
        // If backend isn't reachable, don't block the wizard (Firestore can still be used directly).
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadStage, setUploadStage] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [resumeParseError, setResumeParseError] = useState<string | null>(null);
  const [resumeUploadIssue, setResumeUploadIssue] = useState<string | null>(null);

  const [facts, setFacts] = useState<ConfirmedFacts>({
    fullName: "",
    email: "",
    location: "",
    headline: "",
    yearsExperience: undefined,
    skills: [],
    highlights: [],
  });

  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jd, setJd] = useState("");

  const [selectedModules, setSelectedModules] = useState<Record<ModuleKey, boolean>>({
    benchmark: true,
    gaps: true,
    learningPlan: true,
    cv: true,
    coverLetter: true,
    export: true,
  });

  const generationStartedRef = useRef(false);

  useEffect(() => {
    if (!app) return;
    setJobTitle(app.job.title || "");
    setCompany(app.job.company || "");
    setJd(app.job.description || "");
    if (app.resume.extractedText) setResumeText(app.resume.extractedText);
    if (app.confirmedFacts) setFacts(app.confirmedFacts);
  }, [app]);

  const jdQuality = useMemo(() => computeJDQuality(jd), [jd]);
  const jdKeywords = useMemo(() => extractKeywords(jd), [jd]);

  const goto = (nextStep: number) => {
    const qs = new URLSearchParams(search.toString());
    qs.set("step", String(nextStep));
    if (resolvedAppId) qs.set("appId", resolvedAppId);
    router.push(`/new?${qs.toString()}`);
  };

  const ensureApp = async () => {
    if (!user) return null;
    if (firestoreReady === false) {
      throw new Error(
        "Firestore database isn’t created yet. In Firebase Console go to Build → Firestore Database → Create database (Native mode), then refresh and retry."
      );
    }
    if (resolvedAppId) return resolvedAppId;
    if (!createAppPromiseRef.current) {
      createAppPromiseRef.current = createApplication(user.uid).then((id) => {
        setResolvedAppId(id);
        return id;
      });
    }
    const withTimeout = async <T,>(p: Promise<T>, ms: number, message: string): Promise<T> => {
      return await new Promise<T>((resolve, reject) => {
        const t = setTimeout(() => reject(new Error(message)), ms);
        p.then(
          (v) => {
            clearTimeout(t);
            resolve(v);
          },
          (e) => {
            clearTimeout(t);
            reject(e);
          }
        );
      });
    };

    return await withTimeout(
      createAppPromiseRef.current,
      12_000,
      "Creating workspace timed out. Check Firestore is enabled and you’re online, then retry."
    );
  };

  const nextPaint = () =>
    new Promise<void>((resolve) => {
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(() => resolve());
      } else {
        setTimeout(() => resolve(), 0);
      }
    });

  const withTimeout = async <T,>(p: Promise<T>, ms: number, message: string): Promise<T> => {
    return await new Promise<T>((resolve, reject) => {
      const t = setTimeout(() => reject(new Error(message)), ms);
      p.then(
        (v) => {
          clearTimeout(t);
          resolve(v);
        },
        (e) => {
          clearTimeout(t);
          reject(e);
        }
      );
    });
  };

  const parseResumeViaBackend = async (file: File): Promise<string> => {
    if (!user) throw new Error("Not signed in.");
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) throw new Error("Backend API URL not configured.");

    const token = await user.getIdToken();
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/resume/parse?max_pages=4`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });

    const json = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(json?.detail || `Server parse failed (${res.status})`);
    }
    return json?.text || "";
  };

  const parseResume = async (
    file: File,
    onProgress?: (pct: number, stage: string) => void
  ): Promise<string> => {
    const ext = file.name.toLowerCase().split(".").pop() || "";
    if (ext === "txt" || file.type === "text/plain") {
      onProgress?.(24, "Reading text…");
      return await file.text();
    }

    if (ext === "docx") {
      onProgress?.(24, "Parsing DOCX…");
      const mammoth = await import("mammoth/mammoth.browser");
      const arrayBuffer = await file.arrayBuffer();
      const out = await mammoth.extractRawText({ arrayBuffer });
      return out.value || "";
    }

    if (ext === "pdf" || file.type === "application/pdf") {
      onProgress?.(24, "Parsing PDF on server…");
      return await parseResumeViaBackend(file);
    }

    throw new Error("Unsupported file type for in-browser parsing. Use PDF, DOCX, or TXT.");
  };

  const extractFacts = (text: string): Partial<ConfirmedFacts> => {
    const t = text || "";
    const email = (t.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i) || [])[0] || "";
    const lines = t.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const fullName = lines.find((l) => l.length >= 3 && l.length <= 40 && !l.includes("@")) || "";

    const SKILLS = [
      "typescript",
      "javascript",
      "react",
      "next.js",
      "node",
      "python",
      "fastapi",
      "sql",
      "postgres",
      "firebase",
      "firestore",
      "aws",
      "gcp",
      "docker",
      "kubernetes",
      "tailwind",
      "testing",
      "ci/cd",
    ];
    const lower = t.toLowerCase();
    const skills = SKILLS.filter((s) => lower.includes(s)).slice(0, 12);

    const highlights = lines
      .filter((l) => /^[-*•]\s+/.test(l) || /\b(\d+%|\d+x|\d+\+)\b/.test(l))
      .slice(0, 6)
      .map((l) => l.replace(/^[-*•]\s+/, ""));

    return { email, fullName, skills, highlights };
  };

  const textToHtml = (text: string) => {
    const blocks = (text || "")
      .split(/\n{2,}/)
      .map((b) => b.trim())
      .filter(Boolean);
    return blocks.map((b) => `<p>${b.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</p>`).join("");
  };

  const uploadResumeFileToStorage = async (params: {
    appId: string;
    file: File;
    extractedText: string;
    opId: number;
  }) => {
    if (!user) return;
    const isActive = () => mountedRef.current && params.opId === resumeOpIdRef.current;

    setResumeUploadIssue(null);
    setResumeUploadInFlight(true);

    const storagePath = `users/${user.uid}/applications/${params.appId}/resume/${params.file.name}`;
    const storageRef = ref(storage, storagePath);
    const uploadTask = uploadBytesResumable(storageRef, params.file);
    resumeUploadTaskRef.current = uploadTask;

    try {
      await new Promise<void>((resolve, reject) => {
        let lastBytes = 0;
        let lastProgressAt = Date.now();
        const stallMs = 15_000;

        const interval = setInterval(() => {
          if (!isActive()) {
            clearInterval(interval);
            try {
              uploadTask.cancel();
            } catch {}
            reject(new Error("canceled"));
            return;
          }
          if (Date.now() - lastProgressAt > stallMs) {
            clearInterval(interval);
            try {
              uploadTask.cancel();
            } catch {}
            const err = new Error(
              "Upload stalled. Firebase Storage may be disabled or blocked. Enable Firebase Storage in the Firebase Console (Build → Storage → Get started) and retry."
            );
            // @ts-expect-error attach code for mapping
            err.code = "storage/stalled";
            reject(err);
          }
        }, 3000);

        uploadTask.on(
          "state_changed",
          (snap) => {
            if (!isActive()) return;
            const ratio = snap.totalBytes ? snap.bytesTransferred / snap.totalBytes : 0;
            if (snap.bytesTransferred > lastBytes) {
              lastBytes = snap.bytesTransferred;
              lastProgressAt = Date.now();
            }
            setUploadPct(60 + Math.round(ratio * 35)); // 60..95
            setUploadStage(`Uploading file in background… ${Math.round(ratio * 100)}%`);
          },
          (err) => {
            clearInterval(interval);
            reject(err);
          },
          () => {
            clearInterval(interval);
            resolve();
          }
        );
      });

      if (!isActive()) return;

      const storageUrl = await getDownloadURL(uploadTask.snapshot.ref);
      if (!isActive()) return;

      await patchApplication(params.appId, {
        resume: {
          fileName: params.file.name,
          storagePath,
          storageUrl,
          extractedText: params.extractedText,
        },
      } as any);
      if (!isActive()) return;

      setUploadPct(100);
      setUploadStage("Resume uploaded");
      setTimeout(() => {
        if (!isActive()) return;
        setUploadPct(null);
        setUploadStage(null);
      }, 800);
    } catch (err: any) {
      if (!isActive()) return;
      if (err?.message === "canceled" || err?.code === "storage/canceled") return;
      const code = err?.code as string | undefined;
      const storageErrors: Record<string, string> = {
        "storage/bucket-not-found":
          "Firebase Storage bucket not found. Enable Storage in Firebase Console → Build → Storage → Get started.",
        "storage/unauthorized":
          "Storage permission denied. Check Firebase Storage Rules (for dev, allow authenticated users).",
        "storage/unauthenticated":
          "Not authenticated for Storage upload. Try signing out/in and retry.",
        "storage/retry-limit-exceeded":
          "Upload retry limit exceeded. Check your network and Firebase Storage status.",
        "storage/stalled":
          err?.message ||
          "Upload stalled. Enable Firebase Storage (Build → Storage) and retry.",
      };
      setResumeUploadIssue(
        storageErrors[code || ""] ||
          err?.message ||
          "Failed to upload to Firebase Storage."
      );
      setUploadPct(null);
      setUploadStage(null);
    } finally {
      if (!isActive()) return;
      resumeUploadTaskRef.current = null;
      setResumeUploadInFlight(false);
    }
  };

  const retryResumeUpload = async () => {
    if (!user) return;
    const file = resumeFileRef.current;
    if (!file) return;

    let latestStorageOk: boolean | null = storageReady;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (apiUrl) {
        const res = await fetch(`${apiUrl.replace(/\/$/, "")}/health`, { cache: "no-store" });
        const json = await res.json().catch(() => null);
        const ok = json?.firebase?.storage?.ok;
        if (ok === false) {
          latestStorageOk = false;
          setStorageReady(false);
          setStorageStatusError(json?.firebase?.storage?.error || "Firebase Storage is not ready.");
        } else if (ok === true) {
          latestStorageOk = true;
          setStorageReady(true);
          setStorageStatusError(null);
        }
      }
    } catch {}

    if (latestStorageOk === false && !process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST) {
      setResumeUploadIssue(
        "Firebase Storage still isn’t enabled for this project. Enable Storage (Build → Storage → Get started) then retry."
      );
      return;
    }

    const id = await ensureApp();
    if (!id) return;

    resumeOpIdRef.current += 1;
    const opId = resumeOpIdRef.current;
    try {
      resumeUploadTaskRef.current?.cancel();
    } catch {}
    resumeUploadTaskRef.current = null;

    setResumeParseError(null);
    setResumeUploadIssue(null);
    setUploadPct(60);
    setUploadStage("Retrying file upload…");

    const extracted = ((app?.resume?.extractedText || resumeText) || "").slice(0, 40_000);
    await uploadResumeFileToStorage({ appId: id, file, extractedText: extracted, opId });
  };

  const onUploadResume = async (file: File) => {
    if (!user) return;
    resumeFileRef.current = file;

    // Invalidate any previous resume op + cancel in-flight uploads.
    resumeOpIdRef.current += 1;
    const opId = resumeOpIdRef.current;
    const isActive = () => mountedRef.current && opId === resumeOpIdRef.current;
    try {
      resumeUploadTaskRef.current?.cancel();
    } catch {}
    resumeUploadTaskRef.current = null;
    setResumeUploadInFlight(false);

    setResumeParseError(null);
    setResumeUploadIssue(null);
    setBusy(true);
    setUploadStage("Creating workspace…");
    setUploadPct(10);

    try {
      const id = await ensureApp();
      if (!id || !isActive()) return;

      setUploadPct(20);
      setUploadStage("Parsing resume…");
      await nextPaint();

      const parsed = await withTimeout(
        parseResume(file, (pct, stage) => {
          if (!isActive()) return;
          setUploadPct(pct);
          setUploadStage(stage);
        }),
        20_000,
        "Resume parsing took too long. Try DOCX/TXT or paste your resume text in the preview box."
      );
      if (!isActive()) return;

      setUploadPct(52);
      setUploadStage("Saving parsed resume…");
      await nextPaint();

      const normalized = (parsed || "").slice(0, 40_000);
      setResumeText(parsed);

      const extracted = extractFacts(normalized);
      setFacts((prev) => ({
        ...prev,
        ...extracted,
        skills: extracted.skills || prev.skills,
        highlights: extracted.highlights || prev.highlights,
      }));

      await patchApplication(id, {
        resume: {
          fileName: file.name,
          extractedText: normalized,
        },
        docs: {
          ...(app?.docs || { cv: { contentHtml: "", versions: [], updatedAt: Date.now() }, coverLetter: { contentHtml: "", versions: [], updatedAt: Date.now() } }),
          baseResumeHtml: textToHtml(normalized),
        },
      } as any);
      if (!isActive()) return;

      // From here on, the user can continue. Storage upload happens in the background when available.
      setUploadPct(60);
      setUploadStage("Saved. Uploading file in background…");
      setBusy(false);

      if (storageReady === false && !process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST) {
        // Cloud Storage bucket creation can require billing; fall back to Firestore Bytes for small files.
        const maxInlineBytes = 600 * 1024; // keep well under Firestore 1MB/doc limit
        if (file.size <= maxInlineBytes) {
          setUploadPct(75);
          setUploadStage("Saving file to Firestore (fallback)…");
          await nextPaint();
          try {
            const bytes = Bytes.fromUint8Array(new Uint8Array(await file.arrayBuffer()));
            await patchApplication(id, {
              resume: {
                fileName: file.name,
                extractedText: normalized,
                inlineBytes: bytes,
                inlineMimeType: file.type || "application/octet-stream",
                inlineSize: file.size,
              },
            } as any);
            if (!isActive()) return;
            setResumeUploadIssue(
              "Firebase Storage isn’t enabled (Cloud Storage requires billing). Stored your resume file in Firestore for now. Enable Storage later and click “Retry upload” to also store the PDF in Storage."
            );
            setUploadPct(100);
            setUploadStage("Saved (Firestore fallback)");
          } catch {
            if (!isActive()) return;
            setResumeUploadIssue(
              "Firebase Storage isn’t enabled and Firestore fallback storage failed. You can still continue with the parsed text."
            );
            setUploadPct(null);
            setUploadStage(null);
          }
        } else {
          setResumeUploadIssue(
            "Firebase Storage isn’t enabled, and this file is too large for Firestore fallback. You can still continue with the parsed text; enable Storage to upload the PDF."
          );
          setUploadPct(null);
          setUploadStage(null);
        }

        setTimeout(() => {
          if (!isActive()) return;
          setUploadPct(null);
          setUploadStage(null);
        }, 1200);
        return;
      }

      setUploadStage("Saved. Uploading file in background… 0%");
      void uploadResumeFileToStorage({ appId: id, file, extractedText: normalized, opId });

      return;
    } catch (e: any) {
      setResumeParseError(e?.message || "Failed to parse/upload resume.");
      setUploadPct(null);
      setUploadStage(null);
    } finally {
      setBusy(false);
    }
  };

  const lockFacts = async () => {
    if (!user) return;
    const id = await ensureApp();
    if (!id) return;
    setBusy(true);
    try {
      await patchApplication(id, {
        factsLocked: true,
        confirmedFacts: {
          ...facts,
          skills: (facts.skills || []).map((s) => s.trim()).filter(Boolean),
          highlights: (facts.highlights || []).map((s) => s.trim()).filter(Boolean),
        },
      } as any);
      goto(2);
    } finally {
      setBusy(false);
    }
  };

  const saveJob = async () => {
    if (!user) return;
    const id = await ensureApp();
    if (!id) return;
    setBusy(true);
    try {
      await patchApplication(id, {
        job: {
          title: jobTitle,
          company,
          description: jd,
          quality: jdQuality,
        },
      } as any);
      goto(3);
    } finally {
      setBusy(false);
    }
  };

  const startGeneration = async () => {
    if (!user) return;
    const id = await ensureApp();
    if (!id) return;
    setBusy(true);
    try {
      const include = Object.entries(selectedModules)
        .filter(([, v]) => v)
        .map(([k]) => k as ModuleKey);

      await trackEvent(user.uid, { name: "generate_clicked", appId: id, properties: { include } });

      await Promise.all(
        include.map((m) => setModuleStatus(id, m, { state: "queued", progress: 0 }))
      );
      await patchApplication(id, { status: "generating" } as any);
      goto(4);
    } finally {
      setBusy(false);
    }
  };

  // Step 4: run generation pipeline once.
  useEffect(() => {
    if (!user || !resolvedAppId) return;
    if (step !== 4) return;
    if (!app) return;
    if (generationStartedRef.current) return;

    const queued = (Object.entries(app.modules || {}) as Array<[ModuleKey, any]>)
      .filter(([, s]) => s?.state === "queued")
      .map(([k]) => k);

    if (queued.length === 0) return;
    generationStartedRef.current = true;

    (async () => {
      await generateApplicationModules({
        userId: user.uid,
        appId: resolvedAppId,
        include: queued,
        evidenceCount: evidence.length,
      });
    })();
  }, [app, evidence.length, resolvedAppId, step, user]);

  const canContinue1 = app?.resume?.extractedText || resumeText.trim().length > 0;
  const canContinue2 = jobTitle.trim().length > 0 && jd.trim().length > 0;

  return (
    <div className="space-y-6">
      {/* Wizard header */}
      <div className="rounded-2xl border bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="border bg-blue-50 text-blue-800 border-blue-200">
                Wizard
              </Badge>
              <div className="text-sm font-semibold">New application</div>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Coach-driven workflow: lock facts → sharpen JD → generate modules → open workspace.
            </div>
          </div>
          <div className="flex items-center gap-2">
            {step > 1 ? (
              <Button variant="outline" size="sm" onClick={() => goto(step - 1)} disabled={busy}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            ) : null}
            {step < 4 ? (
              <Button variant="outline" size="sm" onClick={() => router.push("/dashboard")}>
                Exit
              </Button>
            ) : null}
          </div>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <StepChip index={1} active={step === 1} done={!!app?.factsLocked} title="Facts" />
          <StepChip index={2} active={step === 2} done={jdQuality.score >= 50 && !!app?.job?.description} title="Job description" />
          <StepChip index={3} active={step === 3} done={step > 3} title="Confirm & generate" />
          <StepChip index={4} active={step === 4} done={app?.status === "active"} title="Progress" />
        </div>
      </div>

      {step === 1 ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="space-y-4">
            <div className="rounded-2xl border bg-white p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">Step 1 — Upload + parse</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    We extract a preview and propose “confirmed facts”. You must lock what’s true.
                  </div>
                </div>
              </div>

              <div className="mt-4">
                <label className="block text-xs font-medium text-muted-foreground mb-2">
                  Resume file (PDF / DOCX / TXT)
                </label>
                {firestoreReady === false ? (
                  <div className="mb-3 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">
                    <div className="font-medium">Firestore database isn’t created yet.</div>
                    <div className="mt-1 text-red-800/80">
                      Fix: Firebase Console → <span className="font-medium">Build</span> →{" "}
                      <span className="font-medium">Firestore Database</span> →{" "}
                      <span className="font-medium">Create database</span> (Native mode). Then refresh this page.
                    </div>
                    {firestoreStatusError ? (
                      <div className="mt-2 text-[11px] text-red-800/70 break-words">
                        {firestoreStatusError}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {storageReady === false && !process.env.NEXT_PUBLIC_FIREBASE_STORAGE_EMULATOR_HOST ? (
                  <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    <div className="font-medium">Firebase Storage isn’t enabled yet.</div>
                    <div className="mt-1 text-amber-900/80">
                      Your resume text will still be saved, but the file upload will be paused until you enable Storage.
                      Fix: Firebase Console → <span className="font-medium">Build</span> →{" "}
                      <span className="font-medium">Storage</span> → <span className="font-medium">Get started</span>.
                    </div>
                    {storageStatusError ? (
                      <div className="mt-2 text-[11px] text-amber-900/70 break-words">
                        {storageStatusError}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <Input
                    type="file"
                    accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                    disabled={busy || resumeUploadInFlight || firestoreReady === false}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      // Allow selecting the same file again after a failed upload.
                      e.currentTarget.value = "";
                      if (file) onUploadResume(file);
                    }}
                  />
                  <Badge variant="secondary" className="border">
                    {resolvedAppId ? `appId: ${resolvedAppId.slice(0, 8)}…` : "Creating…"}
                  </Badge>
                </div>

                {uploadPct !== null ? (
                  <div className="mt-4">
                    <Progress value={uploadPct} />
                    <div className="mt-1 flex items-center justify-between gap-3">
                      <div className="text-xs text-muted-foreground">
                        {uploadStage ? `${uploadStage} ` : "Working… "}
                        {uploadPct}%
                      </div>
                      {busy || resumeUploadInFlight ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            resumeOpIdRef.current += 1;
                            try {
                              resumeUploadTaskRef.current?.cancel();
                            } catch {}
                            resumeUploadTaskRef.current = null;
                            setResumeUploadInFlight(false);
                            setBusy(false);
                            setUploadPct(null);
                            setUploadStage(null);
                          }}
                        >
                          Cancel
                        </Button>
                      ) : null}
                    </div>
                    {resumeUploadInFlight && !busy ? (
                      <div className="mt-1 text-xs text-muted-foreground">
                        You can continue while the file upload finishes.
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {resumeParseError ? (
                  <div className="mt-4 rounded-xl bg-red-50 p-3 text-xs text-red-700">
                    {resumeParseError}
                    <div className="mt-1 text-red-700/80">
                      MVP fallback: paste your resume text below.
                    </div>
                  </div>
                ) : null}

                {resumeUploadIssue ? (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    <div className="font-medium">Resume file status</div>
                    <div className="mt-1 text-amber-900/80">{resumeUploadIssue}</div>
                    <div className="mt-3 flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={retryResumeUpload}
                        disabled={busy || resumeUploadInFlight || !resumeFileRef.current}
                      >
                        Retry upload
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setResumeUploadIssue(null)}
                        disabled={busy || resumeUploadInFlight}
                      >
                        Dismiss
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl border bg-white p-5">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold">Parse preview</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    This preview is used to seed your base resume and facts. You can edit before locking.
                  </div>
                </div>
                <Badge variant="secondary" className="border">
                  {resumeText.trim().length ? `${resumeText.trim().length.toLocaleString()} chars` : "Empty"}
                </Badge>
              </div>

              <div className="mt-4">
                <Textarea
                  value={resumeText}
                  onChange={(e) => setResumeText(e.target.value)}
                  placeholder="If parsing fails, paste your resume text here…"
                  className="h-56"
                />
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border bg-white p-5">
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-blue-600" />
                <div className="text-sm font-semibold">Confirmed facts</div>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Only lock what you can prove. This prevents “generic AI output”.
              </div>

              <Separator className="my-4" />

              <div className="space-y-3">
                <Field label="Full name">
                  <Input value={facts.fullName || ""} onChange={(e) => setFacts({ ...facts, fullName: e.target.value })} />
                </Field>
                <Field label="Email">
                  <Input value={facts.email || ""} onChange={(e) => setFacts({ ...facts, email: e.target.value })} />
                </Field>
                <Field label="Headline">
                  <Input
                    value={facts.headline || ""}
                    onChange={(e) => setFacts({ ...facts, headline: e.target.value })}
                    placeholder="e.g., Product-minded engineer shipping evidence-backed outcomes"
                  />
                </Field>
                <Field label="Skills (comma-separated)">
                  <Input
                    value={(facts.skills || []).join(", ")}
                    onChange={(e) =>
                      setFacts({
                        ...facts,
                        skills: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      })
                    }
                    placeholder="React, TypeScript, Firebase, SQL…"
                  />
                </Field>
                <Field label="Highlights (one per line)">
                  <Textarea
                    value={(facts.highlights || []).join("\n")}
                    onChange={(e) =>
                      setFacts({
                        ...facts,
                        highlights: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean),
                      })
                    }
                    placeholder="Quantified wins you can defend."
                    className="h-28"
                  />
                </Field>
              </div>

              <div className="mt-4">
                <Button
                  className="w-full gap-2"
                  onClick={async () => {
                    // If user pasted resume text (fallback), store it before locking.
                    if (user && (resumeText || "").trim()) {
                      const id = await ensureApp();
                      if (id) {
                        await patchApplication(id, {
                          resume: { ...(app?.resume || {}), extractedText: resumeText },
                          docs: { ...(app?.docs as any), baseResumeHtml: textToHtml(resumeText) },
                        } as any);
                      }
                    }
                    await lockFacts();
                  }}
                  disabled={busy || !canContinue1 || firestoreReady === false}
                >
                  <Lock className="h-4 w-4" />
                  Lock confirmed facts
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <CoachHint
              title="Coach note"
              body="Facts first. The fastest way to look senior is to remove shaky claims and replace them with proof."
            />
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="rounded-2xl border bg-white p-5">
            <div className="text-sm font-semibold">Step 2 — Job description</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Paste the full JD. The quality meter predicts how good the benchmark/gaps will be.
            </div>

            <Separator className="my-4" />

            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Job title *">
                <Input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="e.g., Senior Frontend Engineer" />
              </Field>
              <Field label="Company">
                <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g., Stripe" />
              </Field>
            </div>

            <div className="mt-4">
              <Field label="Job description *">
                <Textarea value={jd} onChange={(e) => setJd(e.target.value)} className="h-64" placeholder="Paste the posting here…" />
              </Field>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <Button variant="outline" onClick={() => goto(1)} disabled={busy}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button onClick={saveJob} disabled={busy || !canContinue2 || firestoreReady === false}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <QualityCard score={jdQuality.score} issues={jdQuality.issues} suggestions={jdQuality.suggestions} />
            <div className="rounded-2xl border bg-white p-5">
              <div className="text-sm font-semibold">Detected keywords</div>
              <div className="mt-1 text-xs text-muted-foreground">
                These become your targeting set. Missing keywords will generate tasks.
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {jdKeywords.slice(0, 18).map((k) => (
                  <Badge key={k} variant="secondary" className="border text-[11px]">
                    {k}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="rounded-2xl border bg-white p-5">
            <div className="flex items-center gap-2">
              <Wand2 className="h-4 w-4 text-blue-600" />
              <div className="text-sm font-semibold">Step 3 — Confirm outputs</div>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Pick what to generate now. Everything remains editable and versioned.
            </div>

            <Separator className="my-4" />

            <div className="rounded-xl bg-muted/40 p-4">
              <div className="text-sm font-semibold">
                {jobTitle || "Job title"} {company ? <span className="text-muted-foreground">· {company}</span> : null}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Facts locked:{" "}
                <span className="font-medium text-foreground">{app?.factsLocked ? "Yes" : "No"}</span> ·{" "}
                JD quality: <span className="font-medium text-foreground">{jdQuality.score}%</span> ·{" "}
                Keywords: <span className="font-medium text-foreground">{jdKeywords.length}</span>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              <ModulePick
                title="Benchmark"
                desc="Ideal candidate signals + rubric."
                checked={selectedModules.benchmark}
                onChange={(v) => setSelectedModules({ ...selectedModules, benchmark: v })}
              />
              <ModulePick
                title="Gap analysis"
                desc="Missing keywords + recommendations + tasks."
                checked={selectedModules.gaps}
                onChange={(v) => setSelectedModules({ ...selectedModules, gaps: v })}
              />
              <ModulePick
                title="Learning plan"
                desc="Skill sprints + outcomes-based practice."
                checked={selectedModules.learningPlan}
                onChange={(v) => setSelectedModules({ ...selectedModules, learningPlan: v })}
              />
              <ModulePick
                title="Tailored CV"
                desc="Editable, diffable, versioned."
                checked={selectedModules.cv}
                onChange={(v) => setSelectedModules({ ...selectedModules, cv: v })}
              />
              <ModulePick
                title="Cover letter"
                desc="Evidence-first letter, not fluff."
                checked={selectedModules.coverLetter}
                onChange={(v) => setSelectedModules({ ...selectedModules, coverLetter: v })}
              />
              <ModulePick
                title="Export pack"
                desc="Prep for PDF/DOC exports (MVP readiness)."
                checked={selectedModules.export}
                onChange={(v) => setSelectedModules({ ...selectedModules, export: v })}
              />
            </div>

            <div className="mt-4 flex items-center justify-between">
              <Button variant="outline" onClick={() => goto(2)} disabled={busy}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button onClick={startGeneration} disabled={busy || !resolvedAppId}>
                Generate modules
                <Sparkles className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <CoachHint
              title="Coach note"
              body="Generation is just a draft. The quality comes from your iterations: regenerate per module, snapshot versions, and attach evidence."
            />
            <div className="rounded-2xl border bg-white p-5">
              <div className="text-sm font-semibold">What you’ll get</div>
              <div className="mt-1 text-xs text-muted-foreground">
                A workspace that stays explainable: scores + why, tasks + why, and evidence-backed writing.
              </div>
              <Separator className="my-4" />
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                <div>• Sticky scoreboard header</div>
                <div>• Coach panel</div>
                <div>• Action queue</div>
                <div>• Evidence vault</div>
                <div>• Diff mode</div>
                <div>• Version history</div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {step === 4 ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="rounded-2xl border bg-white p-5">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-blue-600" />
              <div className="text-sm font-semibold">Step 4 — Status stepper</div>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Watch modules complete. Then open your workspace and start iterating.
            </div>

            <Separator className="my-4" />

            {!app ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            ) : (
              <StatusStepper modules={app.modules} />
            )}

            <div className="mt-4 flex items-center justify-between">
              <Button variant="outline" onClick={() => goto(3)} disabled={busy}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <Button
                onClick={() => router.push(`/applications/${resolvedAppId}`)}
                disabled={!resolvedAppId || app?.status !== "active"}
              >
                Open workspace
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <CoachHint
              title="Coach note"
              body="When the workspace opens, don’t fix everything. Pick the top fix, ship it, snapshot, repeat."
            />
            <div className="rounded-2xl border bg-white p-5">
              <div className="text-sm font-semibold">While you wait</div>
              <div className="mt-1 text-xs text-muted-foreground">
                Evidence improves everything. Add at least 2 items for your top 2 keywords.
              </div>
              <div className="mt-4 flex items-center justify-between">
                <Badge variant="secondary" className="border tabular-nums">
                  {evidence.length} evidence items
                </Badge>
                <Button variant="outline" size="sm" onClick={() => router.push("/evidence")}>
                  Open vault
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function NewApplicationPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      }
    >
      <PageInner />
    </Suspense>
  );
}

function StepChip({ index, active, done, title }: { index: number; active: boolean; done: boolean; title: string }) {
  return (
    <div
      className={[
        "rounded-xl border px-3 py-2",
        active ? "bg-blue-50 border-blue-200" : "bg-white",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold">Step {index}</div>
        {done ? (
          <Badge variant="secondary" className="border bg-green-50 text-green-800 border-green-200 text-[11px]">
            Done
          </Badge>
        ) : active ? (
          <Badge variant="secondary" className="border text-[11px]">
            Active
          </Badge>
        ) : (
          <Badge variant="secondary" className="border text-[11px]">
            Pending
          </Badge>
        )}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{title}</div>
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

function CoachHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border bg-gradient-to-b from-white to-white/60 p-5">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-1 text-xs text-muted-foreground leading-snug">{body}</div>
    </div>
  );
}

function QualityCard({ score, issues, suggestions }: { score: number; issues: string[]; suggestions: string[] }) {
  return (
    <div className="rounded-2xl border bg-white p-5">
      <div className="text-sm font-semibold">JD quality meter</div>
      <div className="mt-1 text-xs text-muted-foreground">
        Better input = better benchmark, gaps, and tasks.
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs">
          <div className="text-muted-foreground">Score</div>
          <div className="font-semibold tabular-nums">{score}%</div>
        </div>
        <div className="mt-2">
          <Progress value={score} />
        </div>
      </div>

      {issues.length > 0 ? (
        <div className="mt-4 rounded-xl bg-amber-50 p-3">
          <div className="text-xs font-semibold text-amber-900">Issues</div>
          <ul className="mt-2 space-y-1 text-xs text-amber-900/80">
            {issues.slice(0, 4).map((i) => (
              <li key={i}>• {i}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {suggestions.length > 0 ? (
        <div className="mt-3 rounded-xl bg-blue-50 p-3">
          <div className="text-xs font-semibold text-blue-900">Suggestions</div>
          <ul className="mt-2 space-y-1 text-xs text-blue-900/80">
            {suggestions.slice(0, 4).map((i) => (
              <li key={i}>• {i}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function ModulePick({
  title,
  desc,
  checked,
  onChange,
}: {
  title: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 rounded-xl border bg-white p-3 hover:bg-muted/40 transition-colors cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1" />
      <div className="min-w-0">
        <div className="text-sm font-semibold">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground leading-snug">{desc}</div>
      </div>
    </label>
  );
}
