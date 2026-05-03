/**
 * Application Module
 *
 * Job application workflow module.
 * Handles creating, generating, and tracking applications.
 */

// Types
export * from "./types/application";

// Services
export { applicationApi } from "./services/applicationApi";

// Hooks
export {
  // Queries
  useApplications,
  useApplication,
  // Mutations
  useCreateApplication,
  useUpdateApplication,
  useDeleteApplication,
  useGenerateDocuments,
  useMarkAsSent,
  useGenerationProgress,
  // Keys
  applicationKeys,
} from "./hooks/useApplication";
