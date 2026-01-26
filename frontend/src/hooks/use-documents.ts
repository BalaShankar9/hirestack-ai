"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Document, DocumentGenerateRequest } from "@/types"
import { useAuth } from "./use-auth"

export function useDocuments() {
  const { isAuthenticated } = useAuth()
  const queryClient = useQueryClient()

  const {
    data: documents,
    isLoading,
    error,
  } = useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: api.builder.list,
    enabled: isAuthenticated,
  })

  const generateMutation = useMutation({
    mutationFn: (data: DocumentGenerateRequest) => api.builder.generate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      api.builder.update(id, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.builder.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })

  return {
    documents: documents || [],
    isLoading,
    error,
    generate: generateMutation.mutateAsync,
    update: updateMutation.mutateAsync,
    deleteDocument: deleteMutation.mutateAsync,
    isGenerating: generateMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useDocument(documentId: string | null) {
  const { isAuthenticated } = useAuth()

  return useQuery<Document>({
    queryKey: ["document", documentId],
    queryFn: () => api.builder.get(documentId!),
    enabled: isAuthenticated && !!documentId,
  })
}
