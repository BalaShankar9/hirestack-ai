"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Profile } from "@/types"
import { useAuth } from "./use-auth"

export function useProfile() {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: profile,
    isLoading,
    error,
  } = useQuery<Profile>({
    queryKey: ["profile"],
    queryFn: api.profile.get,
    enabled: isAuthenticated,
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.profile.upload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Profile>) => api.profile.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] })
    },
  })

  return {
    profile,
    isLoading,
    error,
    upload: uploadMutation.mutateAsync,
    update: updateMutation.mutateAsync,
    isUploading: uploadMutation.isPending,
    isUpdating: updateMutation.isPending,
  }
}
