"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Benchmark } from "@/types"
import { useAuth } from "./use-auth"

export function useBenchmark(jobId: string | null) {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: benchmark,
    isLoading,
    error,
  } = useQuery<Benchmark>({
    queryKey: ["benchmark", jobId],
    queryFn: () => api.benchmark.getByJob(jobId!),
    enabled: isAuthenticated && !!jobId,
  })

  const generateMutation = useMutation({
    mutationFn: (jobDescriptionId: string) =>
      api.benchmark.generate(jobDescriptionId),
    onSuccess: (_, jobDescriptionId) => {
      queryClient.invalidateQueries({ queryKey: ["benchmark", jobDescriptionId] })
    },
  })

  const regenerateMutation = useMutation({
    mutationFn: (benchmarkId: string) => api.benchmark.regenerate(benchmarkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["benchmark"] })
    },
  })

  return {
    benchmark,
    isLoading,
    error,
    generate: generateMutation.mutateAsync,
    regenerate: regenerateMutation.mutateAsync,
    isGenerating: generateMutation.isPending,
    isRegenerating: regenerateMutation.isPending,
  }
}
