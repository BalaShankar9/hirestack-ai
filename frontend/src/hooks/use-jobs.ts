"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { JobDescription, JobDescriptionCreate } from "@/types"
import { useAuth } from "./use-auth"

export function useJobs() {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: jobs,
    isLoading,
    error,
  } = useQuery<JobDescription[]>({
    queryKey: ["jobs"],
    queryFn: api.jobs.list,
    enabled: isAuthenticated,
  })

  const createMutation = useMutation({
    mutationFn: (data: JobDescriptionCreate) => api.jobs.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.jobs.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  return {
    jobs: jobs || [],
    isLoading,
    error,
    createJob: createMutation.mutateAsync,
    deleteJob: deleteMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useJob(id: string | null) {
  const { isAuthenticated } = useAuth()

  return useQuery<JobDescription>({
    queryKey: ["job", id],
    queryFn: () => api.jobs.get(id!),
    enabled: isAuthenticated && !!id,
  })
}
