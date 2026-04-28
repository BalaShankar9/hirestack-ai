"use client";

/**
 * DocumentEditorTab — thin wrapper that composes the optional VariantPicker
 * with the canonical DocEditorModule.
 *
 * Extracted from `applications/[id]/page.tsx` where four near-identical
 * `<TabsContent>` blocks (cv, cover, statement, portfolio) were copy-pasted
 * around the same DocEditorModule. Centralising the pattern here means:
 *
 *   • New cross-tab capabilities (e.g. an extra header banner) land in one
 *     place instead of drifting across four call-sites.
 *   • Any future tab (resume, etc.) gets the same shape for free.
 *   • The page god-component shrinks materially.
 *
 * NOTE: This is a pure layout/composition wrapper. It owns no state and
 * forwards every DocEditorModule prop verbatim. The parent stays in charge
 * of editor refs, regenerate handlers, version drawers, etc.
 */

import type { DocVariant } from "@/lib/firestore/models";
import type { DocMode } from "@/components/workspace/diff-toggle";
import { DocEditorModule } from "@/components/workspace/doc-editor-module";
import { VariantPicker } from "@/components/editor/variant-picker";

export interface DocumentEditorTabProps {
  /* ── DocEditorModule pass-through props ─────────────────────────── */
  title: string;
  subtitle: string;
  mode: DocMode;
  onModeChange: (m: DocMode) => void;
  keywords: string[];
  missingKeywords: string[];
  isCovered: (k: string) => boolean;
  value: string;
  onChange: (html: string) => void;
  editorRef: any;
  onEditorReady?: (editor: any | null) => void;
  onPickEvidence: () => void;
  onRegenerate: () => void;
  onOpenVersions: () => void;
  baseHtml: string;
  isRegenerating?: boolean;

  /* ── Optional variant-picker config ─────────────────────────────── */
  /**
   * When provided AND `variants.length >= 2`, renders a VariantPicker
   * above the editor. The VariantPicker also self-hides for shorter
   * arrays, so this prop is also safe to pass unconditionally.
   */
  variantPicker?: {
    title: string;
    variants: DocVariant[];
    onLock: (variantKey: string) => Promise<void>;
  };
}

export function DocumentEditorTab(props: DocumentEditorTabProps) {
  const { variantPicker, ...editorProps } = props;

  return (
    <>
      {variantPicker && Array.isArray(variantPicker.variants) && variantPicker.variants.length >= 2 && (
        <VariantPicker
          title={variantPicker.title}
          variants={variantPicker.variants}
          onLock={variantPicker.onLock}
        />
      )}
      <DocEditorModule {...editorProps} />
    </>
  );
}
