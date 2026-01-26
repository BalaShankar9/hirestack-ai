import {
  addDoc,
  deleteDoc,
  getDoc,
  getDocs,
  limit,
  orderBy,
  query,
  setDoc,
  updateDoc,
  where,
} from "firebase/firestore";

import {
  applicationDocRef,
  applicationsCollectionRef,
  userEvidenceDocRef,
  userEvidenceCollectionRef,
  userEventDocRef,
  userEventsCollectionRef,
  userTaskDocRef,
  userTasksCollectionRef,
} from "./paths";

import type {
  AnalyticsEventDoc,
  ApplicationDoc,
  BenchmarkModule,
  CoachActionKind,
  ConfirmedFacts,
  DocModule,
  EvidenceDoc,
  EvidenceKind,
  GapsModule,
  JDQuality,
  LearningPlanModule,
  ModuleKey,
  ModuleStatus,
  ModuleState,
  Scorecard,
  TaskDoc,
  TaskPriority,
  TaskSource,
  TaskStatus,
} from "./models";

export type ApplicationCreateInput = Partial<
  Omit<ApplicationDoc, "id" | "createdAt" | "updatedAt">
> & {
  job?: Partial<ApplicationDoc["job"]>;
};

function now() {
  return Date.now();
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

export function uid(prefix: string = "id") {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function emptyModuleStatus(state: ModuleState = "idle"): ModuleStatus {
  return { state, progress: state === "ready" ? 100 : 0, updatedAt: now() };
}

export function emptyDocModule(seedHtml: string = ""): DocModule {
  return { contentHtml: seedHtml, versions: [], updatedAt: now() };
}

export function computeJDQuality(text: string): JDQuality {
  const t = (text || "").trim();
  const issues: string[] = [];
  const suggestions: string[] = [];

  const len = t.length;
  const lines = t.split(/\r?\n/);
  const hasBullets = lines.filter((l) => /^\s*[-*•]\s+/.test(l)).length >= 3;
  const hasResponsibilities = /responsibilit(y|ies)|what you('|’)ll do/i.test(t);
  const hasRequirements = /requirements|qualifications|must have|you have/i.test(t);
  const hasStackSignals = /(stack|tech|tools|experience with|proficient in)/i.test(t);

  let score = 0;
  if (len < 350) {
    issues.push("Job description is short; signal quality may be low.");
    suggestions.push("Paste the full posting including responsibilities + requirements.");
    score += 15;
  } else if (len < 900) {
    suggestions.push("Include responsibilities, requirements, and tooling sections for better coverage.");
    score += 30;
  } else {
    score += 45;
  }

  if (hasBullets) score += 10;
  else {
    issues.push("Few bullet points detected; hard to extract requirements.");
    suggestions.push("Include bullet lists for responsibilities and requirements.");
  }

  if (hasResponsibilities) score += 15;
  else {
    issues.push("Missing responsibilities section.");
    suggestions.push("Add a responsibilities section or paste that part of the posting.");
  }

  if (hasRequirements) score += 15;
  else {
    issues.push("Missing requirements/qualifications section.");
    suggestions.push("Add requirements/qualifications to improve keyword targeting.");
  }

  if (hasStackSignals) score += 10;
  else suggestions.push("Add the tech stack/tools section if available.");

  score = clamp(score, 0, 100);
  return { score, issues, suggestions };
}

const STOPWORDS = new Set(
  [
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "our",
    "are",
    "will",
    "this",
    "that",
    "from",
    "have",
    "has",
    "was",
    "were",
    "their",
    "they",
    "them",
    "but",
    "not",
    "all",
    "any",
    "can",
    "may",
    "about",
    "into",
    "more",
    "most",
    "work",
    "working",
    "role",
    "team",
    "teams",
    "years",
    "year",
    "experience",
    "including",
    "required",
    "requirements",
    "responsibilities",
    "ability",
    "skills",
    "skill",
    "strong",
    "preferred",
    "plus",
    "using",
  ].map((s) => s.toLowerCase())
);

const KNOWN_SKILLS = [
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
  "gcp",
  "aws",
  "docker",
  "kubernetes",
  "tailwind",
  "testing",
  "jest",
  "vitest",
  "playwright",
  "ci/cd",
  "graphql",
  "rest",
  "microservices",
  "llm",
  "machine learning",
  "data pipelines",
  "etl",
  "spark",
  "kafka",
  "terraform",
];

export function extractKeywords(text: string, max: number = 18): string[] {
  const t = (text || "").toLowerCase();
  const found: string[] = [];

  // seed known skills first
  for (const k of KNOWN_SKILLS) {
    if (t.includes(k)) found.push(k);
  }

  const words = t
    .replace(/[^a-z0-9+/.#\s-]/g, " ")
    .split(/\s+/)
    .map((w) => w.trim())
    .filter(Boolean)
    .filter((w) => w.length >= 3)
    .filter((w) => !STOPWORDS.has(w));

  const freq = new Map<string, number>();
  for (const w of words) {
    freq.set(w, (freq.get(w) || 0) + 1);
  }

  const ranked = Array.from(freq.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([w]) => w)
    .filter((w) => !found.includes(w));

  const merged = [...found, ...ranked].slice(0, max);
  return merged;
}

export function computeMatchScore(confirmed: ConfirmedFacts | null, keywords: string[]): number {
  const skills = new Set((confirmed?.skills || []).map((s) => s.toLowerCase()));
  const k = keywords.map((x) => x.toLowerCase());
  if (k.length === 0) return 0;
  const hit = k.filter((kw) => skills.has(kw)).length;
  return clamp(Math.round((hit / k.length) * 100), 0, 100);
}

export function computeDocCoverageScore(docHtml: string, keywords: string[]): number {
  const text = (docHtml || "").replace(/<[^>]*>/g, " ").toLowerCase();
  if (keywords.length === 0) return 0;
  const hits = keywords.filter((k) => text.includes(k.toLowerCase())).length;
  return clamp(Math.round((hits / keywords.length) * 100), 0, 100);
}

export function deriveTopFix(missingKeywords: string[], quality: JDQuality): string {
  if (missingKeywords.length > 0) {
    return `Add proof + a bullet for “${missingKeywords[0]}”.`;
  }
  if (quality.score < 60) return "Improve JD input quality (paste full posting).";
  return "Tighten the top summary to match the role’s keywords.";
}

export function buildBenchmark(jobTitle: string, company: string | undefined, keywords: string[]): BenchmarkModule {
  const who = company ? `${jobTitle} @ ${company}` : jobTitle;
  const summary =
    `Benchmark for ${who}: ` +
    `signals seniority through measurable impact, crisp ownership boundaries, and keyword-complete narratives across ${keywords.slice(0, 6).join(", ")}.`;

  const rubric = [
    "Impact: metrics + scope per bullet",
    "Ownership: decisions, trade-offs, constraints",
    "Execution: delivery velocity + reliability",
    "Collaboration: cross-functional influence",
    "Craft: architecture, testing, performance",
    "Signal: role keywords appear naturally",
  ];

  return { summary, keywords, rubric, createdAt: now() };
}

export function buildGaps(confirmed: ConfirmedFacts | null, keywords: string[]): GapsModule {
  const skills = new Set((confirmed?.skills || []).map((s) => s.toLowerCase()));
  const missingKeywords = keywords
    .filter((k) => !skills.has(k.toLowerCase()))
    .slice(0, 10);

  const strengths = (confirmed?.skills || []).slice(0, 8);

  const recommendations = [
    "Rewrite 2–3 bullets to include the missing keywords with measurable outcomes.",
    "Add 1 evidence item per critical keyword (link, repo, PR, demo, or doc).",
    "Move the strongest, most relevant proof into the top third of the resume.",
  ];

  return { missingKeywords, strengths, recommendations, createdAt: now() };
}

export function buildLearningPlan(missingKeywords: string[]): LearningPlanModule {
  const focus = missingKeywords.slice(0, 4);
  const themes = focus.length > 0 ? focus : ["role alignment", "proof building", "storytelling"];

  const plan = Array.from({ length: 4 }).map((_, i) => {
    const theme = themes[i % themes.length];
    return {
      week: i + 1,
      theme: `Week ${i + 1}: ${theme}`,
      outcomes: [
        `Ship one proof artifact for ${theme}.`,
        "Translate work into 2 quantified bullets.",
      ],
      tasks: [
        `Build a small artifact demonstrating ${theme}.`,
        "Write a STAR mini-story with metric + constraint + decision.",
        "Add keyword-aligned bullet to tailored CV.",
      ],
    };
  });

  const resources = focus.map((skill) => ({
    title: `Quick sprint: strengthen ${skill}`,
    provider: "HireStack Coach",
    timebox: "60–90 min",
    skill,
  }));

  return { focus, plan, resources, createdAt: now() };
}

function htmlP(text: string) {
  const escaped = (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `<p>${escaped}</p>`;
}

function htmlH2(text: string) {
  const escaped = (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `<h2>${escaped}</h2>`;
}

function htmlUl(items: string[]) {
  const lis = items
    .map((i) => i.trim())
    .filter(Boolean)
    .map((i) => `<li>${i.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`)
    .join("");
  return `<ul>${lis}</ul>`;
}

export function seedCvHtml(
  confirmed: ConfirmedFacts | null,
  jobTitle: string,
  company: string | undefined,
  keywords: string[],
  baseResumeHtml?: string
) {
  const header = [
    `<h1>${(confirmed?.fullName || "Your Name").replace(/</g, "&lt;")}</h1>`,
    htmlP(confirmed?.headline || `Targeting ${jobTitle}${company ? ` @ ${company}` : ""}`),
  ].join("");

  const keySkills = keywords.slice(0, 12);
  const skillBlock =
    htmlH2("Role Keywords") +
    htmlP("These are the signals recruiters and ATS will scan for. Keep them honest: only claim what you can prove.") +
    htmlUl(keySkills);

  const proofBlock =
    htmlH2("Proof Hooks") +
    htmlP("Add 2–3 bullets below that prove the keywords with outcomes (metric + scope + constraint).") +
    htmlUl([
      "Reduced build time by 35% by redesigning CI pipeline (Docker, caching, parallelization).",
      "Improved API p95 latency by 42% via query optimization and caching (SQL, profiling).",
    ]);

  const baseBlock = baseResumeHtml ? htmlH2("Base Resume (Imported)") + baseResumeHtml : "";

  return header + skillBlock + proofBlock + baseBlock;
}

export function seedCoverLetterHtml(
  confirmed: ConfirmedFacts | null,
  jobTitle: string,
  company: string | undefined,
  keywords: string[]
) {
  const who = company || "your team";
  const k = keywords.slice(0, 5).join(", ");
  const p1 = `I’m applying for the ${jobTitle} role. I build outcomes-first systems and communicate trade-offs clearly—especially around ${k}.`;
  const p2 =
    "What you’ll get from me in week one: a crisp plan, a tight feedback loop, and proof artifacts that de-risk hiring decisions.";
  const p3 =
    "If helpful, I can share a short evidence pack (links, demos, PRs) aligned to your top requirements.";
  return (
    `<h1>Cover Letter</h1>` +
    htmlP(`To ${who},`) +
    htmlP(p1) +
    htmlP(p2) +
    htmlP(p3) +
    htmlP(`— ${confirmed?.fullName || "Your Name"}`)
  );
}

export function buildScorecard(params: {
  match: number;
  ats: number;
  scan: number;
  evidence: number;
  topFix: string;
}): Scorecard {
  const n = now();
  return {
    match: clamp(params.match, 0, 100),
    atsReadiness: clamp(params.ats, 0, 100),
    recruiterScan: clamp(params.scan, 0, 100),
    evidenceStrength: clamp(params.evidence, 0, 100),
    topFix: params.topFix,
    updatedAt: n,
  };
}

export async function createApplication(userId: string, input: ApplicationCreateInput = {}) {
  const n = now();
  const jobQuality = input.job?.quality || { score: 0, issues: [], suggestions: [] };
  const job = {
    title: input.job?.title || "",
    company: input.job?.company || "",
    description: input.job?.description || "",
    quality: jobQuality,
  };

  const base: Omit<ApplicationDoc, "id"> = {
    userId,
    createdAt: n,
    updatedAt: n,
    status: "draft",
    job,
    resume: input.resume || {},
    factsLocked: input.factsLocked ?? false,
    confirmedFacts: input.confirmedFacts ?? null,
    modules: {
      benchmark: emptyModuleStatus(),
      gaps: emptyModuleStatus(),
      learningPlan: emptyModuleStatus(),
      cv: emptyModuleStatus(),
      coverLetter: emptyModuleStatus(),
      export: emptyModuleStatus(),
    },
    scores: buildScorecard({
      match: 0,
      ats: 0,
      scan: 0,
      evidence: 0,
      topFix: "Start by locking your confirmed facts.",
    }),
    docs: {
      baseResumeHtml: input.docs?.baseResumeHtml || "",
      cv: input.docs?.cv || emptyDocModule(""),
      coverLetter: input.docs?.coverLetter || emptyDocModule(""),
    },
  };

  const docRef = await addDoc(applicationsCollectionRef(), base);
  return docRef.id;
}

export async function getApplication(appId: string): Promise<ApplicationDoc | null> {
  const snap = await getDoc(applicationDocRef(appId));
  if (!snap.exists()) return null;
  return { id: snap.id, ...(snap.data() as Omit<ApplicationDoc, "id">) };
}

export async function patchApplication(appId: string, patch: Partial<Omit<ApplicationDoc, "id" | "userId" | "createdAt">>) {
  await updateDoc(applicationDocRef(appId), { ...patch, updatedAt: now() } as any);
}

export async function setModuleStatus(appId: string, module: ModuleKey, status: Partial<ModuleStatus>) {
  const n = now();
  await updateDoc(applicationDocRef(appId), {
    [`modules.${module}`]: {
      ...(status as any),
      updatedAt: n,
      state: status.state || "idle",
      progress: typeof status.progress === "number" ? status.progress : 0,
    },
    updatedAt: n,
  });
}

export async function snapshotDocVersion(appId: string, which: "cv" | "coverLetter", label: string) {
  const app = await getApplication(appId);
  if (!app) return;
  const current = app.docs[which].contentHtml || "";
  const versionId = uid("v");
  const version = { id: versionId, label, createdAt: now(), contentHtml: current };
  const versions = [version, ...(app.docs[which].versions || [])].slice(0, 20);
  await updateDoc(applicationDocRef(appId), {
    [`docs.${which}.versions`]: versions,
    [`docs.${which}.updatedAt`]: now(),
    updatedAt: now(),
  });
}

export async function restoreDocVersion(appId: string, which: "cv" | "coverLetter", versionId: string) {
  const app = await getApplication(appId);
  if (!app) return;
  const v = (app.docs[which].versions || []).find((x) => x.id === versionId);
  if (!v) return;
  await updateDoc(applicationDocRef(appId), {
    [`docs.${which}.contentHtml`]: v.contentHtml,
    [`docs.${which}.updatedAt`]: now(),
    updatedAt: now(),
  });
}

export async function createEvidence(
  userId: string,
  input: Omit<EvidenceDoc, "id" | "userId" | "createdAt" | "updatedAt">
) {
  const n = now();
  const ref = await addDoc(userEvidenceCollectionRef(userId), {
    ...input,
    userId,
    createdAt: n,
    updatedAt: n,
  });
  return ref.id;
}

export async function updateEvidence(
  userId: string,
  evidenceId: string,
  patch: Partial<Omit<EvidenceDoc, "id" | "userId" | "createdAt">>
) {
  await updateDoc(userEvidenceDocRef(userId, evidenceId), { ...patch, updatedAt: now() } as any);
}

export async function deleteEvidence(userId: string, evidenceId: string) {
  await deleteDoc(userEvidenceDocRef(userId, evidenceId));
}

export async function upsertTask(
  userId: string,
  taskId: string,
  task: Omit<TaskDoc, "id" | "userId" | "createdAt"> & { createdAt?: number }
) {
  const n = now();
  await setDoc(
    userTaskDocRef(userId, taskId),
    {
      ...task,
      userId,
      createdAt: task.createdAt ?? n,
    },
    { merge: true }
  );
}

export async function setTaskStatus(userId: string, taskId: string, status: TaskStatus) {
  const patch: Partial<TaskDoc> = {
    status,
    completedAt: status === "done" ? now() : undefined,
  };
  await updateDoc(userTaskDocRef(userId, taskId), patch as any);
}

export async function trackEvent(
  userId: string,
  event: Omit<AnalyticsEventDoc, "id" | "userId" | "createdAt">
) {
  const id = uid("evt");
  await setDoc(userEventDocRef(userId, id), {
    ...event,
    id,
    userId,
    createdAt: now(),
  });
}

function slugifyId(input: string) {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function taskIdFor(appId: string, slug: string) {
  return `${appId}__${slugifyId(slug)}`;
}

export async function syncGapTasks(userId: string, appId: string, missing: string[]) {
  const base: Omit<TaskDoc, "id" | "userId"> = {
    appId,
    source: "gaps",
    module: "gaps",
    title: "",
    priority: "high",
    status: "todo",
    createdAt: now(),
    tags: [],
  };

  const top = missing.slice(0, 6);
  await Promise.all(
    top.map(async (kw, i) => {
      const id = taskIdFor(appId, `gap-proof-${kw}`);
      await upsertTask(userId, id, {
        ...base,
        title: `Add proof for “${kw}”`,
        detail: "Attach a link/file and write a quantified bullet using it.",
        why: "Keywords without proof read like claims. Proof converts claims into signal.",
        priority: i < 2 ? "high" : "medium",
        tags: ["evidence", kw],
      });
    })
  );
}

export async function syncLearningTasks(userId: string, appId: string, plan: LearningPlanModule) {
  const focus = plan.focus.slice(0, 4);
  await Promise.all(
    focus.map(async (skill) => {
      const id = taskIdFor(appId, `learn-${skill}`);
      await upsertTask(userId, id, {
        appId,
        source: "learningPlan",
        module: "learningPlan",
        title: `Sprint: strengthen ${skill}`,
        detail: "Spend 60–90 minutes producing an artifact (demo, PR, doc, benchmark).",
        why: "Targeted reps build confidence and yield evidence you can ship.",
        priority: "medium",
        status: "todo",
        tags: ["learning", skill],
      });
    })
  );
}

export function buildCoachActions(params: {
  missingKeywords: string[];
  factsLocked: boolean;
  evidenceCount: number;
}): Array<{ kind: CoachActionKind; title: string; why: string; cta: string }> {
  if (!params.factsLocked) {
    return [
      {
        kind: "review",
        title: "Lock your confirmed facts",
        why: "We only optimize what you can stand behind. Locked facts prevent hallucinated claims.",
        cta: "Lock facts",
      },
    ];
  }

  if (params.evidenceCount === 0) {
    return [
      {
        kind: "collect",
        title: "Add 2 evidence items",
        why: "Evidence makes your keywords credible and improves recruiter scan speed.",
        cta: "Open Evidence Vault",
      },
    ];
  }

  if (params.missingKeywords.length > 0) {
    const kw = params.missingKeywords[0];
    return [
      {
        kind: "fix",
        title: `Add “${kw}” to a top bullet (with proof)`,
        why: "Missing keywords reduce ATS match and weaken the 6‑second scan.",
        cta: "Open CV editor",
      },
    ];
  }

  return [
    {
      kind: "write",
      title: "Snapshot this version",
      why: "Versioning lets you iterate safely and compare improvements.",
      cta: "Save snapshot",
    },
  ];
}

export async function generateApplicationModules(params: {
  userId: string;
  appId: string;
  include: ModuleKey[];
  evidenceCount: number;
  onStep?: (module: ModuleKey, state: ModuleState, progress: number) => void;
}) {
  const { userId, appId, include, evidenceCount, onStep } = params;
  const app = await getApplication(appId);
  if (!app) return;

  const quality = computeJDQuality(app.job.description || "");
  const keywords = extractKeywords(app.job.description || "");
  const confirmed = app.confirmedFacts;

  const missingKeywords = buildGaps(confirmed, keywords).missingKeywords;

  // helper to simulate progress updates (client-side MVP)
  const tick = async (module: ModuleKey, pct: number) => {
    onStep?.(module, "generating", pct);
    await setModuleStatus(appId, module, { state: "generating", progress: pct });
    await new Promise((r) => setTimeout(r, 260));
  };

  await patchApplication(appId, {
    status: "generating",
    job: { ...app.job, quality },
    modules: {
      ...app.modules,
      ...Object.fromEntries(include.map((m) => [m, emptyModuleStatus("queued")])),
    } as any,
  });

  for (const module of include) {
    await tick(module, 10);
    await tick(module, 35);

    if (module === "benchmark") {
      const benchmark = buildBenchmark(app.job.title, app.job.company, keywords);
      await patchApplication(appId, { benchmark } as any);
      await tick(module, 70);
    }

    if (module === "gaps") {
      const gaps = buildGaps(confirmed, keywords);
      await patchApplication(appId, { gaps } as any);
      await syncGapTasks(userId, appId, gaps.missingKeywords);
      await tick(module, 70);
    }

    if (module === "learningPlan") {
      const plan = buildLearningPlan(missingKeywords);
      await patchApplication(appId, { learningPlan: plan } as any);
      await syncLearningTasks(userId, appId, plan);
      await tick(module, 70);
    }

    if (module === "cv") {
      const html = seedCvHtml(confirmed, app.job.title, app.job.company, keywords, app.docs.baseResumeHtml);
      await patchApplication(appId, {
        docs: { ...app.docs, cv: { ...app.docs.cv, contentHtml: html, updatedAt: now() } },
      } as any);
      await tick(module, 70);
    }

    if (module === "coverLetter") {
      const html = seedCoverLetterHtml(confirmed, app.job.title, app.job.company, keywords);
      await patchApplication(appId, {
        docs: { ...app.docs, coverLetter: { ...app.docs.coverLetter, contentHtml: html, updatedAt: now() } },
      } as any);
      await tick(module, 70);
    }

    if (module === "export") {
      // No heavy export pipeline in MVP. We keep this module as a readiness indicator.
      await tick(module, 70);
    }

    // finalize module
    await setModuleStatus(appId, module, { state: "ready", progress: 100 });
    onStep?.(module, "ready", 100);
  }

  const ats = computeDocCoverageScore(app.docs.cv.contentHtml || "", keywords);
  const scan = clamp(45 + Math.round(ats * 0.35), 0, 100);
  const match = computeMatchScore(confirmed, keywords);
  const evidence = clamp(evidenceCount * 18, 0, 100);
  const topFix = deriveTopFix(missingKeywords, quality);

  await patchApplication(appId, {
    status: "active",
    scores: buildScorecard({ match, ats, scan, evidence, topFix }),
  } as any);
}

export async function regenerateModule(params: {
  userId: string;
  appId: string;
  module: ModuleKey;
  evidenceCount: number;
}) {
  await generateApplicationModules({
    userId: params.userId,
    appId: params.appId,
    include: [params.module],
    evidenceCount: params.evidenceCount,
  });
}

export async function listApplicationsForUser(userId: string, max: number = 50) {
  const q = query(
    applicationsCollectionRef(),
    where("userId", "==", userId),
    orderBy("updatedAt", "desc"),
    limit(max)
  );
  const snaps = await getDocs(q);
  return snaps.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<ApplicationDoc, "id">) }));
}

export async function listEvidence(userId: string, max: number = 100) {
  const q = query(userEvidenceCollectionRef(userId), orderBy("updatedAt", "desc"), limit(max));
  const snaps = await getDocs(q);
  return snaps.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<EvidenceDoc, "id">) }));
}

export async function listTasks(userId: string, appId?: string, max: number = 200) {
  const base = userTasksCollectionRef(userId);
  const q = appId
    ? query(base, where("appId", "==", appId), orderBy("createdAt", "desc"), limit(max))
    : query(base, orderBy("createdAt", "desc"), limit(max));
  const snaps = await getDocs(q);
  return snaps.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<TaskDoc, "id">) }));
}
