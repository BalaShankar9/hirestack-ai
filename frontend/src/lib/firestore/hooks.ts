"use client";

import { useEffect, useMemo, useState } from "react";
import {
  onSnapshot,
  orderBy,
  query,
  where,
  limit,
  type Unsubscribe,
} from "firebase/firestore";

import type { ApplicationDoc, EvidenceDoc, TaskDoc } from "./models";
import {
  applicationDocRef,
  applicationsCollectionRef,
  userEvidenceCollectionRef,
  userTasksCollectionRef,
} from "./paths";

export function useApplication(appId: string | null) {
  const [data, setData] = useState<ApplicationDoc | null>(null);
  const [loading, setLoading] = useState(!!appId);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!appId) return;
    setLoading(true);
    const unsub = onSnapshot(
      applicationDocRef(appId),
      (snap) => {
        if (!snap.exists()) {
          setData(null);
        } else {
          setData({ id: snap.id, ...(snap.data() as Omit<ApplicationDoc, "id">) });
        }
        setError(null);
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      }
    );
    return () => unsub();
  }, [appId]);

  return { data, loading, error };
}

export function useApplications(userId: string | null, max: number = 50) {
  const [data, setData] = useState<ApplicationDoc[]>([]);
  const [loading, setLoading] = useState(!!userId);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);

    const q = query(
      applicationsCollectionRef(),
      where("userId", "==", userId),
      orderBy("updatedAt", "desc"),
      limit(max)
    );

    const unsub = onSnapshot(
      q,
      (snaps) => {
        const apps = snaps.docs.map((d) => ({
          id: d.id,
          ...(d.data() as Omit<ApplicationDoc, "id">),
        }));
        setData(apps);
        setError(null);
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      }
    );

    return () => unsub();
  }, [max, userId]);

  return { data, loading, error };
}

export function useEvidence(userId: string | null, max: number = 100) {
  const [data, setData] = useState<EvidenceDoc[]>([]);
  const [loading, setLoading] = useState(!!userId);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);

    const q = query(userEvidenceCollectionRef(userId), orderBy("updatedAt", "desc"), limit(max));
    const unsub = onSnapshot(
      q,
      (snaps) => {
        setData(snaps.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<EvidenceDoc, "id">) })));
        setError(null);
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      }
    );

    return () => unsub();
  }, [max, userId]);

  return { data, loading, error };
}

export function useTasks(userId: string | null, appId?: string | null, max: number = 200) {
  const [data, setData] = useState<TaskDoc[]>([]);
  const [loading, setLoading] = useState(!!userId);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);

    const base = userTasksCollectionRef(userId);
    const q = appId
      ? query(base, where("appId", "==", appId), orderBy("createdAt", "desc"), limit(max))
      : query(base, orderBy("createdAt", "desc"), limit(max));

    const unsub = onSnapshot(
      q,
      (snaps) => {
        setData(snaps.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<TaskDoc, "id">) })));
        setError(null);
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      }
    );

    return () => unsub();
  }, [appId, max, userId]);

  const stats = useMemo(() => {
    const done = data.filter((t) => t.status === "done").length;
    return {
      total: data.length,
      done,
      remaining: Math.max(0, data.length - done),
      completionPct: data.length ? Math.round((done / data.length) * 100) : 0,
    };
  }, [data]);

  return { data, loading, error, stats };
}

