# HireStack AI — Application Intelligence Workspace (UX Spec v1)

Date: 2026-01-25

This document describes the implemented IA, page layouts, component APIs, and Firestore contract for the “application intelligence workspace” experience (coach-driven, explainable, action-based, iterative).

---

## 1) Information Architecture + Navigation

### Global shell (AppShell)
- **Sidebar (primary nav)**
  - `/dashboard` — Workspaces + action queue
  - `/new` — New Application Wizard
  - `/evidence` — Evidence Vault
  - `/career` — Career Lab
  - **Recent workspaces** list (latest updated)
- **Topbar (sticky)**
  - Page title + hint
  - Command palette trigger (⌘K / Ctrl+K)
- **Command palette**
  - Navigate to main pages
  - Jump to recent workspaces

### Primary UX objects (consistent patterns)
- **Application Workspace** (per application)
- **Sticky Scoreboard Header** (per workspace)
- **Sticky Coach Panel** (right rail)
- **Action Queue** (tasks from gaps/learning plan)
- **Evidence Vault** (proof items, reusable across applications)
- **Editor patterns**
  - Two-pane: editor + keyword/suggestion rail
  - Diff mode: base resume vs tailored
  - Version history snapshots (v1/v2…)
  - Per-module regeneration

---

## 2) Pages (layouts + states)

### `/dashboard` — Workspaces + queue
**Layout**
- Hero: “Diagnose → plan → build proof → ship → track”
- Stats: active workspaces, open tasks, evidence count, avg match
- Workspace list: cards with match + micro-metrics + “Top fix”
- Right rail: compact TaskQueue + Evidence pulse

**States**
- Skeleton loaders for app/task/evidence queries
- Empty: CTA to `/new` wizard

### `/new` — New Application Wizard
**Core workflow**
1) **Upload + parse + preview**  
   - In-browser parsing (PDF/DOCX/TXT)
   - Preview panel
   - “Lock confirmed facts” (factsLocked gate)
2) **JD input + quality meter**
   - JD quality score + issues/suggestions
   - Keyword preview (chips)
3) **Confirm outputs + Generate**
   - Select modules to generate
   - Generate click triggers event + queues module statuses
4) **Status stepper (not a spinner)**
   - Per-module progress (benchmark/gaps/learning/cv/cover/export)
   - “Open workspace” CTA when ready

**States**
- Wizard step chips (active/done)
- Per-step validation gates (facts locked, JD present)
- Generation shows stepper + module states

### `/applications/[id]` — Application Workspace (the product)
**Layout**
- Sticky **ScoreboardHeader**: match, ATS, 6‑second scan, evidence strength, top fix
- Main area: Tabs + module content
- Right sticky **CoachPanel**: next-best actions + “why it matters”

**Tabs**
- **Overview**: ModuleCard grid + TaskQueue
- **Benchmark**: benchmark summary + rubric (regenerate)
- **Gap analysis**: missing keywords + recommendations (regenerate)
- **Learning plan**: week-by-week sprints + resources (regenerate)
- **Tailored CV**: Two-pane editor (edit/diff) + keywords + suggestions + versions + evidence insert
- **Cover letter**: Same editor pattern
- **Export**: Download HTML + copy text (tracks export_clicked)

**States**
- Workspace skeleton (scoreboard + main + coach)
- Empty states per module when not generated
- Error states per module (ModuleStatus.error)

### `/evidence` — Evidence Vault
**Layout**
- Header: explanation + search + “Add evidence”
- Tabs: All / Links / Files / Suggested evidence to collect
- Grid of EvidenceCard with “Use in CV”

**Insert flow**
- “Use in CV” opens a workspace picker dialog
- Navigates to `/applications/[id]?tab=cv&insertEvidence={evidenceId}`
- Workspace auto-inserts a proof bullet at cursor when editor is ready

**States**
- Skeleton grid while loading
- Empty: coach guidance + CTA to add evidence

### `/career` — Career Lab
**Layout**
- Learning tasks derived from tasks collection (learningPlan source)
- Lightweight resource panel from the most recent active application

---

## 3) Firestore contract (typed)

Implementation lives in:
- `frontend/src/lib/firestore/models.ts`
- `frontend/src/lib/firestore/paths.ts`
- `frontend/src/lib/firestore/ops.ts`
- `frontend/src/lib/firestore/hooks.ts`

### Collections
- `applications/{appId}`
  - `status`, `scores`, `modules`
  - `benchmark`, `gaps`, `learningPlan`
  - `docs.baseResumeHtml`, `docs.cv`, `docs.coverLetter`
- `users/{uid}/evidence/{evidenceId}`
  - `kind: link|file`, `title`, `url|storageUrl`, `tags/skills/tools`
- `users/{uid}/tasks/{taskId}`
  - `status`, `priority`, `source`, optional `appId`, tags
- `users/{uid}/events/{eventId}` (analytics)
  - `name` ∈ `view_workspace | generate_clicked | export_clicked | task_completed`

---

## 4) Component system (props/interfaces)

### Shell
- `frontend/src/components/app-shell.tsx`
  - `AppShell({ children, pageTitle?, pageHint?, actions? })`

### Workspace core
- `frontend/src/components/workspace/scoreboard-header.tsx`
  - `ScoreboardHeader({ title, subtitle?, scorecard })`
- `frontend/src/components/workspace/coach-panel.tsx`
  - `CoachPanel({ actions, statusLine? })`
  - `CoachAction = { kind, title, why, cta, onClick? }`
- `frontend/src/components/workspace/module-card.tsx`
  - `ModuleCard({ title, description, status, icon, onOpen?, onRegenerate? })`
- `frontend/src/components/workspace/status-stepper.tsx`
  - `StatusStepper({ modules, order? })`
- `frontend/src/components/workspace/task-queue.tsx`
  - `TaskQueue({ tasks, onToggle, onOpenWorkspace?, compact? })`

### Evidence
- `frontend/src/components/workspace/evidence-card.tsx`
  - `EvidenceCard({ evidence, onUse?, onOpen? })`
- `frontend/src/components/workspace/evidence-picker.tsx`
  - `EvidencePicker({ open, onOpenChange, evidence, onPick })`

### Editor helpers
- `frontend/src/components/editor/tiptap-editor.tsx`
  - `TipTapEditor({ content?, onChange?, placeholder?, editable?, className?, editorRef?, onReady? })`
- `frontend/src/components/workspace/keyword-chips.tsx`
  - `KeywordChips({ keywords, isCovered, limit? })`
- `frontend/src/components/workspace/diff-toggle.tsx`
  - `DiffToggle({ mode, onChange })`
- `frontend/src/components/workspace/version-history-drawer.tsx`
  - `VersionHistoryDrawer({ open, onOpenChange, versions, onSnapshot, onRestore })`

---

## 5) Analytics (minimal)

Events are recorded via `trackEvent()` to `users/{uid}/events/*`.
- `generate_clicked` — when user clicks “Generate” in `/new`
- `view_workspace` — when `/applications/[id]` loads
- `export_clicked` — when a user exports CV/cover in Export tab
- `task_completed` — when a task transitions to done

---

## 6) File tree (frontend, key paths)

Key pages:
- `frontend/src/app/(dashboard)/dashboard/page.tsx`
- `frontend/src/app/(dashboard)/new/page.tsx`
- `frontend/src/app/(dashboard)/applications/[id]/page.tsx`
- `frontend/src/app/(dashboard)/evidence/page.tsx`
- `frontend/src/app/(dashboard)/career/page.tsx`

Core system:
- `frontend/src/components/app-shell.tsx`
- `frontend/src/components/workspace/*`
- `frontend/src/components/editor/tiptap-editor.tsx`
- `frontend/src/lib/firestore/*`

