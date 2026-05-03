/**
 * Application Hooks
 *
 * TanStack Query hooks for application data fetching and mutations.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
  type UseMutationOptions,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { applicationApi } from "../services/applicationApi";
import type {
  Application,
  CreateApplicationRequest,
  GenerationRequest,
  GenerationProgress,
} from "../types/application";

// Query keys for cache management
export const applicationKeys = {
  all: ["applications"] as const,
  lists: () => [...applicationKeys.all, "list"] as const,
  list: (filters: string) => [...applicationKeys.lists(), { filters }] as const,
  details: () => [...applicationKeys.all, "detail"] as const,
  detail: (id: string) => [...applicationKeys.details(), id] as const,
  progress: (id: string) => [...applicationKeys.detail(id), "progress"] as const,
};

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get all applications for the current user.
 */
export function useApplications(
  options?: Omit<UseQueryOptions<Application[], Error>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: applicationKeys.lists(),
    queryFn: () => applicationApi.getAll(),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/**
 * Get a single application by ID.
 */
export function useApplication(
  applicationId: string,
  options?: Omit<UseQueryOptions<Application, Error>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: applicationKeys.detail(applicationId),
    queryFn: () => applicationApi.getById(applicationId),
    enabled: !!applicationId,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create a new application.
 */
export function useCreateApplication(
  options?: Omit<
    UseMutationOptions<Application, Error, CreateApplicationRequest>,
    "mutationFn"
  >
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => applicationApi.create(data),
    onSuccess: (newApplication) => {
      queryClient.invalidateQueries({ queryKey: applicationKeys.lists() });
      queryClient.setQueryData(
        applicationKeys.detail(newApplication.id),
        newApplication
      );
    },
    ...options,
  });
}

/**
 * Update an application.
 */
export function useUpdateApplication(
  options?: Omit<
    UseMutationOptions<
      Application,
      Error,
      { applicationId: string; updates: Partial<Application> }
    >,
    "mutationFn"
  >
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ applicationId, updates }) =>
      applicationApi.update(applicationId, updates),
    onSuccess: (updatedApplication, variables) => {
      queryClient.setQueryData(
        applicationKeys.detail(variables.applicationId),
        updatedApplication
      );
      queryClient.invalidateQueries({ queryKey: applicationKeys.lists() });
    },
    ...options,
  });
}

/**
 * Delete an application.
 */
export function useDeleteApplication(
  options?: Omit<UseMutationOptions<void, Error, string>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (applicationId: string) => applicationApi.delete(applicationId),
    onSuccess: (_, deletedId) => {
      queryClient.removeQueries({ queryKey: applicationKeys.detail(deletedId) });
      queryClient.invalidateQueries({ queryKey: applicationKeys.lists() });
    },
    ...options,
  });
}

/**
 * Generate documents for an application.
 */
export function useGenerateDocuments(
  options?: Omit<
    UseMutationOptions<void, Error, { applicationId: string; request: GenerationRequest }>,
    "mutationFn"
  >
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ applicationId, request }) =>
      applicationApi.generate(applicationId, request),
    onSuccess: (_, variables) => {
      // Invalidate to trigger re-fetch with new documents
      queryClient.invalidateQueries({
        queryKey: applicationKeys.detail(variables.applicationId),
      });
    },
    ...options,
  });
}

/**
 * Mark application as sent.
 */
export function useMarkAsSent(
  options?: Omit<UseMutationOptions<Application, Error, string>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (applicationId: string) => applicationApi.markAsSent(applicationId),
    onSuccess: (updatedApplication) => {
      queryClient.setQueryData(
        applicationKeys.detail(updatedApplication.id),
        updatedApplication
      );
      queryClient.invalidateQueries({ queryKey: applicationKeys.lists() });
    },
    ...options,
  });
}

/**
 * Hook to stream generation progress.
 */
export function useGenerationProgress(applicationId: string | null) {
  const [progress, setProgress] = useState<GenerationProgress | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!applicationId) return;

    let eventSource: EventSource | null = null;
    setIsConnected(true);
    setError(null);

    const connect = () => {
      eventSource = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/applications/${applicationId}/progress`
      );

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as GenerationProgress;
          setProgress(data);
        } catch (err) {
          console.error("Failed to parse progress update:", err);
        }
      };

      eventSource.onerror = (err) => {
        setError(new Error("Connection lost"));
        setIsConnected(false);
        eventSource?.close();
      };
    };

    connect();

    return () => {
      eventSource?.close();
      setIsConnected(false);
    };
  }, [applicationId]);

  return { progress, isConnected, error };
}
