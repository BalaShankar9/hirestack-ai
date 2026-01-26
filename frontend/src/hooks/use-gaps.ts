"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { GapReport, GapAnalyzeRequest } from "@/types"
import { useAuth } from "./use-auth"

export function useGaps() {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: reports,
    isLoading,
    error,
  } = useQuery<GapReport[]>({
    queryKey: ["gap-reports"],
    queryFn: api.gaps.list,
    enabled: isAuthenticated,
  })

  const analyzeMutation = useMutation({
    mutationFn: (data: GapAnalyzeRequest) => api.gaps.analyze(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gap-reports"] })
    },
  })

  const refreshMutation = useMutation({
    mutationFn: (reportId: string) => api.gaps.refresh(reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gap-reports"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (reportId: string) => api.gaps.delete(reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gap-reports"] })
    },
  })

  return {
    reports: reports || [],
    isLoading,
    error,
    analyze: analyzeMutation.mutateAsync,
    refresh: refreshMutation.mutateAsync,
    deleteReport: deleteMutation.mutateAsync,
    isAnalyzing: analyzeMutation.isPending,
    isRefreshing: refreshMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useGapReport(reportId: string | null) {
  const { isAuthenticated } = useAuth()

  return useQuery<GapReport>({
    queryKey: ["gap-report", reportId],
    queryFn: () => api.gaps.get(reportId!),
    enabled: isAuthenticated && !!reportId,
  })
}
