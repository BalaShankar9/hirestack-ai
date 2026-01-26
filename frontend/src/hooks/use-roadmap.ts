"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Roadmap, RoadmapGenerateRequest } from "@/types"
import { useAuth } from "./use-auth"

export function useRoadmaps() {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: roadmaps,
    isLoading,
    error,
  } = useQuery<Roadmap[]>({
    queryKey: ["roadmaps"],
    queryFn: api.consultant.listRoadmaps,
    enabled: isAuthenticated,
  })

  const generateMutation = useMutation({
    mutationFn: (data: RoadmapGenerateRequest) =>
      api.consultant.generateRoadmap(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roadmaps"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (roadmapId: string) => api.consultant.deleteRoadmap(roadmapId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roadmaps"] })
    },
  })

  return {
    roadmaps: roadmaps || [],
    isLoading,
    error,
    generate: generateMutation.mutateAsync,
    deleteRoadmap: deleteMutation.mutateAsync,
    isGenerating: generateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useRoadmap(roadmapId: string | null) {
  const { isAuthenticated } = useAuth()

  return useQuery<Roadmap>({
    queryKey: ["roadmap", roadmapId],
    queryFn: () => api.consultant.getRoadmap(roadmapId!),
    enabled: isAuthenticated && !!roadmapId,
  })
}
