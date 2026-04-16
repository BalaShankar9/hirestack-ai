/**
 * Real-time hooks — Supabase Realtime subscriptions.
 *
 * Replaces Firestore onSnapshot hooks.
 * Import path stays `@/lib/firestore/hooks` for backward compat.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { TABLES } from "./paths";
import type {
  ApplicationDoc,
  EvidenceDoc,
  GenerationJobDoc,
  GenerationJobEventDoc,
  TaskDoc,
} from "./models";
import {
  mapApplicationRow,
  mapEvidenceRow,
  mapGenerationJobEventRow,
  mapGenerationJobRow,
  mapTaskRow,
} from "./ops";

const REALTIME_DEBUG =
  process.env.NEXT_PUBLIC_REALTIME_DEBUG === "1" ||
  process.env.NEXT_PUBLIC_REALTIME_DEBUG === "true";

const ENABLE_REALTIME_ENV = (process.env.NEXT_PUBLIC_ENABLE_REALTIME ?? "").toLowerCase();
// Default OFF to avoid noisy websocket errors in local dev; polling is the baseline.
const REALTIME_ENABLED_BY_ENV =
  ["1", "true", "on", "yes"].includes(ENABLE_REALTIME_ENV);

let REALTIME_DISABLED = false;

const ACTIVE_GENERATION_JOB_STATUSES = new Set(["queued", "running"]);

function realtimeWarn(...args: any[]) {
  if (!REALTIME_DEBUG) return;
  // eslint-disable-next-line no-console
  console.warn(...args);
}

function shouldUseRealtime(): boolean {
  return REALTIME_ENABLED_BY_ENV && !REALTIME_DISABLED;
}

function disableRealtimeOnce(reason: string, err?: unknown) {
  if (REALTIME_DISABLED) return;
  REALTIME_DISABLED = true;
  realtimeWarn("[HireStack][realtime] disabled:", reason, err);
}

function isDocumentHidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function isActiveGenerationJobStatus(status: string | null | undefined): boolean {
  if (!status) return true;
  return ACTIVE_GENERATION_JOB_STATUSES.has(status);
}

/**
 * Schedule a realtime re-enable after a backoff period.
 * This allows hooks to recover from transient websocket disconnects
 * without requiring a full page reload.
 */
let _realtimeResetTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleRealtimeReset(delayMs: number) {
  if (_realtimeResetTimer) return; // already scheduled
  _realtimeResetTimer = setTimeout(() => {
    _realtimeResetTimer = null;
    REALTIME_DISABLED = false;
    realtimeWarn("[HireStack][realtime] attempting reconnect after backoff");
  }, delayMs);
}

/* ------------------------------------------------------------------ */
/*  Generic helper                                                      */
/* ------------------------------------------------------------------ */

interface UseRealtimeResult<T extends { id: string }> {
  data: T[];
  loading: boolean;
  error: Error | null;
  /** Optimistically add an item — instant UI update even if realtime is flaky */
  addItem: (item: T) => void;
  /** Optimistically remove an item by id — instant UI update before real-time fires */
  removeItem: (id: string) => void;
  /** Optimistically update an item by id */
  updateItem: (id: string, patch: Partial<T>) => void;
}

/* ------------------------------------------------------------------ */
/*  useApplications — all apps for a user                              */
/* ------------------------------------------------------------------ */

export function useApplications(
  userId: string | null,
  limit = 50
): UseRealtimeResult<ApplicationDoc> {
  const [data, setData] = useState<ApplicationDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) {
      setData([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    let poll: ReturnType<typeof setInterval> | null = null;

    function startPolling() {
      if (poll) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchInitial();
      }, 10_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    // Initial fetch
    async function fetchInitial() {
      try {
        const { data: rows, error: err } = await supabase
          .from(TABLES.applications)
          .select("*")
          .eq("user_id", userId)
          .order("updated_at", { ascending: false })
          .limit(limit);

        if (err) throw err;
        if (!cancelled) {
          setData((rows ?? []).map(mapApplicationRow));
          setLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchInitial();

    // If realtime is disabled (env or runtime failure), use polling only.
    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    // Realtime subscription
    const channel = supabase
      .channel(`applications:${userId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.applications,
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            setData((prev) => [mapApplicationRow(payload.new), ...prev]);
          } else if (payload.eventType === "UPDATE") {
            setData((prev) =>
              prev.map((a) =>
                a.id === payload.new.id ? mapApplicationRow(payload.new) : a
              )
            );
          } else if (payload.eventType === "DELETE") {
            setData((prev) =>
              prev.filter((a) => a.id !== payload.old.id)
            );
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          // Schedule reconnect attempt after 30s so mobile/flaky-wifi users recover
          scheduleRealtimeReset(30_000);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][applications]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [userId, limit]);

  const addItem = useCallback((item: ApplicationDoc) => {
    setData((prev) => (prev.some((a) => a.id === item.id) ? prev : [item, ...prev]));
  }, []);

  const removeItem = useCallback((id: string) => {
    setData((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const updateItem = useCallback((id: string, patch: Partial<ApplicationDoc>) => {
    setData((prev) => prev.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  }, []);

  return { data, loading, error, addItem, removeItem, updateItem };
}

/* ------------------------------------------------------------------ */
/*  useApplication — single app by id                                  */
/* ------------------------------------------------------------------ */

export function useApplication(
  appId: string | null
): { data: ApplicationDoc | null; loading: boolean; error: Error | null } {
  const [data, setData] = useState<ApplicationDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!appId) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    let poll: ReturnType<typeof setInterval> | null = null;

    function startPolling() {
      if (poll) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchOne();
      }, 10_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    async function fetchOne() {
      try {
        const { data: row, error: err } = await supabase
          .from(TABLES.applications)
          .select("*")
          .eq("id", appId)
          .maybeSingle();

        if (err) throw err;
        if (!cancelled) {
          setData(row ? mapApplicationRow(row) : null);
          setLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchOne();

    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    const channel = supabase
      .channel(`application:${appId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.applications,
          filter: `id=eq.${appId}`,
        },
        (payload) => {
          if (payload.eventType === "DELETE") {
            setData(null);
          } else {
            setData(mapApplicationRow(payload.new));
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][application]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [appId]);

  return { data, loading, error };
}

/* ------------------------------------------------------------------ */
/*  useEvidence — evidence items for a user (optionally per app)       */
/* ------------------------------------------------------------------ */

export function useEvidence(
  userId: string | null,
  applicationIdOrLimit?: string | number | null,
  limit?: number
): UseRealtimeResult<EvidenceDoc> {
  // Support both (userId, limit) and (userId, appId, limit) signatures
  const applicationId: string | null =
    typeof applicationIdOrLimit === "string" ? applicationIdOrLimit : null;
  const effectiveLimit: number =
    typeof applicationIdOrLimit === "number"
      ? applicationIdOrLimit
      : limit ?? 100;
  const [data, setData] = useState<EvidenceDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) {
      setData([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    let poll: ReturnType<typeof setInterval> | null = null;

    function startPolling() {
      if (poll) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchInitial();
      }, 10_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    async function fetchInitial() {
      try {
        let q = supabase
          .from(TABLES.evidence)
          .select("*")
          .eq("user_id", userId)
          .order("created_at", { ascending: false })
          .limit(effectiveLimit);

        if (applicationId) {
          q = q.eq("application_id", applicationId);
        }

        const { data: rows, error: err } = await q;
        if (err) throw err;
        if (!cancelled) {
          setData((rows ?? []).map(mapEvidenceRow));
          setLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchInitial();

    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    const filter = applicationId
      ? `user_id=eq.${userId},application_id=eq.${applicationId}`
      : `user_id=eq.${userId}`;

    const channel = supabase
      .channel(`evidence:${userId}:${applicationId ?? "all"}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.evidence,
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            const doc = mapEvidenceRow(payload.new);
            if (!applicationId || doc.applicationId === applicationId) {
              setData((prev) => [doc, ...prev]);
            }
          } else if (payload.eventType === "UPDATE") {
            setData((prev) =>
              prev.map((e) =>
                e.id === payload.new.id ? mapEvidenceRow(payload.new) : e
              )
            );
          } else if (payload.eventType === "DELETE") {
            setData((prev) => prev.filter((e) => e.id !== payload.old.id));
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][evidence]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [userId, applicationId, effectiveLimit]);

  const addItem = useCallback((item: EvidenceDoc) => {
    setData((prev) => (prev.some((e) => e.id === item.id) ? prev : [item, ...prev]));
  }, []);

  const removeItem = useCallback((id: string) => {
    setData((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const updateItem = useCallback((id: string, patch: Partial<EvidenceDoc>) => {
    setData((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }, []);

  return { data, loading, error, addItem, removeItem, updateItem };
}

/* ------------------------------------------------------------------ */
/*  useTasks — tasks for a user (optionally per app)                   */
/* ------------------------------------------------------------------ */

interface TaskStats {
  total: number;
  done: number;
  remaining: number;
}

interface UseTasksResult extends UseRealtimeResult<TaskDoc> {
  stats: TaskStats;
}

export function useTasks(
  userId: string | null,
  applicationId?: string | null,
  limit = 200
): UseTasksResult {
  const [data, setData] = useState<TaskDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) {
      setData([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    let poll: ReturnType<typeof setInterval> | null = null;

    function startPolling() {
      if (poll) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchInitial();
      }, 10_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    async function fetchInitial() {
      try {
        let q = supabase
          .from(TABLES.tasks)
          .select("*")
          .eq("user_id", userId)
          .order("created_at", { ascending: false })
          .limit(limit);

        if (applicationId) {
          q = q.eq("application_id", applicationId);
        }

        const { data: rows, error: err } = await q;
        if (err) throw err;
        if (!cancelled) {
          setData((rows ?? []).map(mapTaskRow));
          setLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchInitial();

    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    const channel = supabase
      .channel(`tasks:${userId}:${applicationId ?? "all"}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.tasks,
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            const doc = mapTaskRow(payload.new);
            if (!applicationId || doc.applicationId === applicationId) {
              setData((prev) => [doc, ...prev]);
            }
          } else if (payload.eventType === "UPDATE") {
            setData((prev) =>
              prev.map((t) =>
                t.id === payload.new.id ? mapTaskRow(payload.new) : t
              )
            );
          } else if (payload.eventType === "DELETE") {
            setData((prev) => prev.filter((t) => t.id !== payload.old.id));
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][tasks]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [userId, applicationId, limit]);

  const addItem = useCallback((item: TaskDoc) => {
    setData((prev) => (prev.some((t) => t.id === item.id) ? prev : [item, ...prev]));
  }, []);

  const removeItem = useCallback((id: string) => {
    setData((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const updateItem = useCallback((id: string, patch: Partial<TaskDoc>) => {
    setData((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  const stats: TaskStats = {
    total: data.length,
    done: data.filter((t) => t.status === "done" || t.status === "skipped").length,
    remaining: data.filter((t) => t.status !== "done" && t.status !== "skipped").length,
  };

  return { data, loading, error, stats, addItem, removeItem, updateItem };
}

export function useGenerationJob(
  jobId: string | null
): { data: GenerationJobDoc | null; loading: boolean; error: Error | null } {
  const [data, setData] = useState<GenerationJobDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!jobId) {
      setData(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    let latestStatus: string | null = null;

    function startPolling() {
      if (poll) return;
      if (!isActiveGenerationJobStatus(latestStatus)) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchOne();
      }, 2_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    async function fetchOne() {
      try {
        const { data: row, error: err } = await supabase
          .from(TABLES.generationJobs)
          .select("*")
          .eq("id", jobId)
          .maybeSingle();

        if (err) throw err;
        if (!cancelled) {
          const next = row ? mapGenerationJobRow(row) : null;
          latestStatus = next?.status ?? null;
          setData(next);
          setLoading(false);
          if (!isActiveGenerationJobStatus(latestStatus)) {
            stopPolling();
          }
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchOne();

    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    const channel = supabase
      .channel(`generation-job:${jobId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.generationJobs,
          filter: `id=eq.${jobId}`,
        },
        (payload) => {
          if (payload.eventType === "DELETE") {
            latestStatus = null;
            setData(null);
          } else {
            const next = mapGenerationJobRow(payload.new);
            latestStatus = next.status ?? null;
            setData(next);
            if (!isActiveGenerationJobStatus(latestStatus)) {
              stopPolling();
            }
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][generationJob]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [jobId]);

  return { data, loading, error };
}

export function useGenerationJobEvents(
  jobId: string | null,
  limit = 500,
  opts?: { live?: boolean }
): { data: GenerationJobEventDoc[]; loading: boolean; error: Error | null } {
  const [data, setData] = useState<GenerationJobEventDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const live = opts?.live ?? true;

  useEffect(() => {
    if (!jobId) {
      setData([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | null = null;
    let lastSequenceNo = 0;

    function startPolling() {
      if (poll) return;
      if (!live) return;
      poll = setInterval(() => {
        if (isDocumentHidden()) return;
        void fetchEvents(false);
      }, 2_000);
    }

    function stopPolling() {
      if (!poll) return;
      clearInterval(poll);
      poll = null;
    }

    async function fetchEvents(forceFullRefresh = false) {
      try {
        let query = supabase
          .from(TABLES.generationJobEvents)
          .select("*")
          .eq("job_id", jobId)
          .order("sequence_no", { ascending: true });

        if (!forceFullRefresh && lastSequenceNo > 0) {
          query = query.gt("sequence_no", lastSequenceNo);
        }

        query = query.limit(limit);

        const { data: rows, error: err } = await query;

        if (err) throw err;
        if (!cancelled) {
          const mapped = (rows ?? []).map(mapGenerationJobEventRow);
          const maxSequenceNo = mapped.length > 0
            ? Math.max(...mapped.map((row) => row.sequenceNo))
            : lastSequenceNo;

          if (forceFullRefresh || lastSequenceNo === 0) {
            setData(mapped.slice(-limit));
          } else if (mapped.length > 0) {
            setData((prev) => {
              const merged = [...prev, ...mapped].reduce<GenerationJobEventDoc[]>((acc, row) => {
                if (acc.some((existing) => existing.id === row.id)) return acc;
                acc.push(row);
                return acc;
              }, []);

              return merged
                .sort((a, b) => a.sequenceNo - b.sequenceNo)
                .slice(-limit);
            });
          }

          lastSequenceNo = maxSequenceNo;
          setLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e);
          setLoading(false);
        }
      }
    }

    fetchEvents(true);

    if (!shouldUseRealtime()) {
      startPolling();
      return () => {
        cancelled = true;
        stopPolling();
      };
    }

    const channel = supabase
      .channel(`generation-job-events:${jobId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: TABLES.generationJobEvents,
          filter: `job_id=eq.${jobId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            const next = mapGenerationJobEventRow(payload.new);
            lastSequenceNo = Math.max(lastSequenceNo, next.sequenceNo);
            setData((prev) => {
              const filtered = prev.filter((row) => row.id !== next.id);
              return [...filtered, next]
                .sort((a, b) => a.sequenceNo - b.sequenceNo)
                .slice(-limit);
            });
          } else if (payload.eventType === "UPDATE") {
            const next = mapGenerationJobEventRow(payload.new);
            setData((prev) =>
              prev.map((row) => (row.id === next.id ? next : row))
            );
          } else if (payload.eventType === "DELETE") {
            setData((prev) => prev.filter((row) => row.id !== String(payload.old.id)));
          }
        }
      )
      .subscribe((status, err) => {
        if (cancelled) return;
        if (status === "SUBSCRIBED") {
          stopPolling();
          return;
        }
        if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setError(err ?? new Error(`Realtime subscription error: ${status}`));
          startPolling();
          disableRealtimeOnce(status, err);
          supabase.removeChannel(channel);
          realtimeWarn("[HireStack][realtime][generationJobEvents]", status, err);
        } else if (status === "CLOSED") {
          startPolling();
        }
      });

    return () => {
      cancelled = true;
      stopPolling();
      supabase.removeChannel(channel);
    };
  }, [jobId, limit, live]);

  return { data, loading, error };
}
