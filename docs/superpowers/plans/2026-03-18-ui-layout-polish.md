# UI Layout & Document Display Polish — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix document display so CVs/letters render as formatted documents by default (view mode), with an explicit Edit button to enter editing — plus fix layout, color, and navigation issues across the app.

**Architecture:** Add a "view" mode to DocEditorModule that renders sanitized HTML with prose styling (like benchmark CV), update the mode toggle to support view/edit/diff, fix the app shell navigation to include all feature pages, and copy missing feature pages from main repo into the worktree.

**Tech Stack:** Next.js 14, React, TailwindCSS, TipTap, shadcn/ui, DOMPurify for HTML sanitization

---

## Tasks

### Task 1: Update mode toggle to support view/edit/diff
- Modify `frontend/src/components/workspace/diff-toggle.tsx`

### Task 2: Add document preview view to DocEditorModule
- Modify `frontend/src/components/workspace/doc-editor-module.tsx`

### Task 3: Default documents to view mode
- Modify `frontend/src/app/(dashboard)/applications/[id]/page.tsx`

### Task 4: Add feature pages to sidebar navigation
- Modify `frontend/src/components/app-shell.tsx`

### Task 5: Copy missing feature pages from main repo

### Task 6: Add doc-preview CSS class
- Modify `frontend/src/app/globals.css`

### Task 7: Fix benchmark CV to use consistent styling

### Task 8: Commit all runtime fixes from this session
