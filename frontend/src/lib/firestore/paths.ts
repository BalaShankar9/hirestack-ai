/**
 * Table name constants — maps to Supabase PostgreSQL tables.
 *
 * Replaces the old Firestore collection/doc reference helpers.
 * Import path stays `@/lib/firestore/paths` for backward compat.
 */

export const TABLES = {
  applications: "applications",
  evidence: "evidence",
  tasks: "tasks",
  events: "events",
  users: "users",
  profiles: "profiles",
  jobs: "job_descriptions",
  benchmarks: "benchmarks",
  gapReports: "gap_reports",
  learningPlans: "learning_plans",
  documents: "documents",
  docVersions: "doc_versions",
  generationJobs: "generation_jobs",
  generationJobEvents: "generation_job_events",
  // Knowledge Library & Global Skills
  knowledgeResources: "knowledge_resources",
  userKnowledgeProgress: "user_knowledge_progress",
  userSkills: "user_skills",
  userSkillGaps: "user_skill_gaps",
  userLearningGoals: "user_learning_goals",
  resourceRecommendations: "resource_recommendations",
} as const;

export type TableName = (typeof TABLES)[keyof typeof TABLES];
