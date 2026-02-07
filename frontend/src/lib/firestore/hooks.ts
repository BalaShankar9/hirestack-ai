/**
 * Real-time hooks — Supabase Realtime subscriptions.
 *
 * Replaces Firestore onSnapshot hooks.
 * Import path stays `@/lib/firestore/hooks` for backward compat.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { TABLES } from "./paths";
import type {
  ApplicationDoc,
  EvidenceDoc,
  TaskDoc,
} from "./models";
import {
  mapApplicationRow,
  mapEvidenceRow,
  mapTaskRow,
} from "./ops";

/* ------------------------------------------------------------------ */
/*  Generic helper                                                      */
/* ------------------------------------------------------------------ */

interface UseRealtimeResult<T> {
  data: T[];
  loading: boolean;
  error: Error | null;
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
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [userId, limit]);

  return { data, loading, error };
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
      .subscribe();

    return () => {
      cancelled = true;
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
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [userId, applicationId, effectiveLimit]);

  return { data, loading, error };
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
      .subscribe();

    return () => {
      cancelled = true;
      supabase.removeChannel(channel);
    };
  }, [userId, applicationId, limit]);

  const stats: TaskStats = {
    total: data.length,
    done: data.filter((t) => t.status === "done" || t.status === "skipped").length,
    remaining: data.filter((t) => t.status !== "done" && t.status !== "skipped").length,
  };

  return { data, loading, error, stats };
}
