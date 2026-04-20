/**
 * W5 UX: debounced company-intel prefetch.
 *
 * When the user lands on the pipeline / workspace page with a job
 * description selected, we speculatively ask the backend to warm up
 * company intel via POST /api/intel/prefetch. By the time they click
 * Generate, the 7-sub-agent intel swarm has usually already finished
 * and sits in JDAnalysisCache — so Recon resolves in milliseconds
 * instead of 8-20 seconds.
 *
 * Contract:
 *   - Debounced 1.2s so we don't thrash when the user is still typing
 *     / picking a job.
 *   - Requires all four fields (jd_text, job_title, company). No-ops
 *     otherwise.
 *   - Fire-and-forget: failures are silently swallowed. This hook
 *     NEVER throws and NEVER triggers a re-render for the consumer
 *     beyond the built-in state machine below.
 *   - Returns an opaque status object ('idle' | 'pending' | 'cached' |
 *     'queued' | 'failed') so the UI can surface a subtle indicator
 *     ("Warming up intel…") if it wants. No indicator is required.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type PrefetchStatus = "idle" | "pending" | "cached" | "queued" | "failed";

export interface UseIntelPrefetchParams {
  jd_text?: string | null;
  job_title?: string | null;
  company?: string | null;
  company_url?: string | null;
  /** Disable entirely (e.g. on first render while data is still loading). */
  disabled?: boolean;
  /** Debounce window in ms; defaults to 1200. */
  debounceMs?: number;
}

const MIN_JD_LEN = 50;

export function useIntelPrefetch(params: UseIntelPrefetchParams): {
  status: PrefetchStatus;
  jdHash: string | null;
} {
  const { jd_text, job_title, company, company_url, disabled, debounceMs = 1200 } = params;
  const [status, setStatus] = useState<PrefetchStatus>("idle");
  const [jdHash, setJdHash] = useState<string | null>(null);

  // Stable tombstone so we only prefetch once per (jd, title, company) tuple.
  const lastKeyRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (disabled) return;

    const jd = (jd_text || "").trim();
    const title = (job_title || "").trim();
    const co = (company || "").trim();

    if (jd.length < MIN_JD_LEN || !title || !co) {
      return;
    }

    // Dedupe — don't hammer the endpoint on re-renders with same input.
    const key = `${jd.length}|${title}|${co}|${(company_url || "").trim()}`;
    if (key === lastKeyRef.current) return;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      lastKeyRef.current = key;
      setStatus("pending");
      const result = await api.prefetchIntel({
        jd_text: jd,
        job_title: title,
        company: co,
        company_url: company_url?.trim() || null,
      });
      if (!result) {
        setStatus("failed");
        return;
      }
      setJdHash(result.jd_hash);
      setStatus(result.status === "cached" ? "cached" : result.status === "queued" ? "queued" : "failed");
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jd_text, job_title, company, company_url, disabled, debounceMs]);

  return { status, jdHash };
}
