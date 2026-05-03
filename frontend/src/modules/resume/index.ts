/**
 * Resume Module
 *
 * Feature-complete resume management module.
 * Includes upload, editing, ATS scoring, and optimization.
 */

// Types
export * from "./types/resume";

// Services
export { resumeApi } from "./services/resumeApi";

// Hooks
export {
  // Queries
  useResumes,
  useResume,
  useATSScore,
  useSuggestions,
  // Mutations
  useUploadResume,
  useCreateResume,
  useUpdateResume,
  useDeleteResume,
  useOptimizeResume,
  useApplySuggestion,
  // Keys
  resumeKeys,
} from "./hooks/useResume";

// Components (to be implemented)
// export { ResumeUploader } from "./components/ResumeUploader";
// export { ResumeEditor } from "./components/ResumeEditor";
// export { ATSScoreCard } from "./components/ATSScoreCard";
// export { OptimizationPanel } from "./components/OptimizationPanel";
