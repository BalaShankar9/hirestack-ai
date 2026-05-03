/**
 * Resume Hooks
 *
 * TanStack Query hooks for resume data fetching and mutations.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
  type UseMutationOptions,
} from "@tanstack/react-query";
import { resumeApi } from "../services/resumeApi";
import type {
  Resume,
  ResumeUploadResult,
  ATSScore,
  OptimizationSuggestion,
  ResumeOptimizationRequest,
} from "../types/resume";

// Query keys for cache management
export const resumeKeys = {
  all: ["resumes"] as const,
  lists: () => [...resumeKeys.all, "list"] as const,
  list: (filters: string) => [...resumeKeys.lists(), { filters }] as const,
  details: () => [...resumeKeys.all, "detail"] as const,
  detail: (id: string) => [...resumeKeys.details(), id] as const,
  atsScore: (id: string) => [...resumeKeys.detail(id), "ats"] as const,
  suggestions: (id: string) => [...resumeKeys.detail(id), "suggestions"] as const,
};

// ─────────────────────────────────────────────────────────────────────────────
// Queries
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Get all resumes for the current user.
 */
export function useResumes(options?: Omit<UseQueryOptions<Resume[], Error>, "queryKey" | "queryFn">) {
  return useQuery({
    queryKey: resumeKeys.lists(),
    queryFn: () => resumeApi.getAll(),
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
}

/**
 * Get a single resume by ID.
 */
export function useResume(
  resumeId: string,
  options?: Omit<UseQueryOptions<Resume, Error>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: resumeKeys.detail(resumeId),
    queryFn: () => resumeApi.getById(resumeId),
    enabled: !!resumeId,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/**
 * Get ATS score for a resume.
 */
export function useATSScore(
  resumeId: string,
  options?: Omit<UseQueryOptions<ATSScore, Error>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: resumeKeys.atsScore(resumeId),
    queryFn: () => resumeApi.getATSScore(resumeId),
    enabled: !!resumeId,
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
}

/**
 * Get optimization suggestions for a resume.
 */
export function useSuggestions(
  resumeId: string,
  options?: Omit<UseQueryOptions<OptimizationSuggestion[], Error>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: resumeKeys.suggestions(resumeId),
    queryFn: () => resumeApi.getSuggestions(resumeId),
    enabled: !!resumeId,
    ...options,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutations
// ─────────────────────────────────────────────────────────────────────────────

interface UploadMutationVariables {
  file: File;
}

/**
 * Upload a resume file.
 */
export function useUploadResume(
  options?: Omit<UseMutationOptions<ResumeUploadResult, Error, UploadMutationVariables>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file }) => resumeApi.upload({ file }),
    onSuccess: () => {
      // Invalidate the resumes list to show the new upload
      queryClient.invalidateQueries({ queryKey: resumeKeys.lists() });
    },
    ...options,
  });
}

interface CreateMutationVariables {
  title: string;
  content: string;
}

/**
 * Create a new resume.
 */
export function useCreateResume(
  options?: Omit<UseMutationOptions<Resume, Error, CreateMutationVariables>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ title, content }) => resumeApi.create({ title, content }),
    onSuccess: (newResume) => {
      queryClient.invalidateQueries({ queryKey: resumeKeys.lists() });
      queryClient.setQueryData(resumeKeys.detail(newResume.id), newResume);
    },
    ...options,
  });
}

interface UpdateMutationVariables {
  resumeId: string;
  updates: Partial<Resume>;
}

/**
 * Update a resume.
 */
export function useUpdateResume(
  options?: Omit<UseMutationOptions<Resume, Error, UpdateMutationVariables>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ resumeId, updates }) => resumeApi.update({ resumeId, updates }),
    onSuccess: (updatedResume, variables) => {
      // Optimistic update
      queryClient.setQueryData(resumeKeys.detail(variables.resumeId), updatedResume);
      queryClient.invalidateQueries({ queryKey: resumeKeys.lists() });
    },
    ...options,
  });
}

/**
 * Delete a resume.
 */
export function useDeleteResume(
  options?: Omit<UseMutationOptions<void, Error, string>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (resumeId: string) => resumeApi.delete(resumeId),
    onSuccess: (_, deletedId) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: resumeKeys.detail(deletedId) });
      queryClient.invalidateQueries({ queryKey: resumeKeys.lists() });
    },
    ...options,
  });
}

/**
 * Optimize a resume for a target job.
 */
export function useOptimizeResume(
  options?: Omit<UseMutationOptions<Resume, Error, ResumeOptimizationRequest>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request) => resumeApi.optimize(request),
    onSuccess: (optimizedResume) => {
      queryClient.setQueryData(resumeKeys.detail(optimizedResume.id), optimizedResume);
      // Also invalidate suggestions since they may have changed
      queryClient.invalidateQueries({ queryKey: resumeKeys.suggestions(optimizedResume.id) });
    },
    ...options,
  });
}

interface ApplySuggestionVariables {
  resumeId: string;
  suggestionId: string;
}

/**
 * Apply an optimization suggestion.
 */
export function useApplySuggestion(
  options?: Omit<UseMutationOptions<Resume, Error, ApplySuggestionVariables>, "mutationFn">
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ resumeId, suggestionId }) => resumeApi.applySuggestion(resumeId, suggestionId),
    onSuccess: (updatedResume, variables) => {
      queryClient.setQueryData(resumeKeys.detail(variables.resumeId), updatedResume);
      queryClient.invalidateQueries({ queryKey: resumeKeys.suggestions(variables.resumeId) });
    },
    ...options,
  });
}
