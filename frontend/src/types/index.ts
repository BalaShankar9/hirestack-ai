// HireStack AI - TypeScript Types

export interface User {
  id: string;
  email: string;
  full_name?: string;
  avatar_url?: string;
  is_active: boolean;
  is_premium: boolean;
  created_at: string;
  updated_at: string;
}

export interface Profile {
  id: string;
  user_id: string;
  name?: string;
  title?: string;
  summary?: string;
  contact_info?: ContactInfo;
  skills?: Skill[];
  experience?: Experience[];
  education?: Education[];
  certifications?: Certification[];
  projects?: Project[];
  languages?: Language[];
  achievements?: string[];
  social_links?: ProfileSocialLinks;
  universal_documents?: UniversalDocuments;
  profile_version?: number;
  universal_docs_version?: number;
  completeness_score?: number;
  resume_worth_score?: number;
  raw_resume_text?: string;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface SocialLinkEntry {
  url: string;
  status?: "linked" | "connected" | "error";
  data?: Record<string, any>;
  connected_at?: string;
  error?: string;
}

export interface ProfileSocialLinks {
  linkedin?: string | SocialLinkEntry;
  github?: string | SocialLinkEntry;
  website?: string | SocialLinkEntry;
  twitter?: string | SocialLinkEntry;
  other?: string;
}

/** Extract URL from a social link entry (handles old string format + new object format) */
export function getSocialUrl(entry: string | SocialLinkEntry | undefined): string {
  if (!entry) return "";
  if (typeof entry === "string") return entry;
  return entry.url || "";
}

/** Get connection status from a social link entry */
export function getSocialStatus(entry: string | SocialLinkEntry | undefined): "none" | "linked" | "connected" | "error" {
  if (!entry) return "none";
  if (typeof entry === "string") return entry ? "linked" : "none";
  return entry.status || "none";
}

export interface UniversalDocuments {
  universal_resume_html?: string;
  full_cv_html?: string;
  personal_statement_html?: string;
  portfolio_html?: string;
  generated_at?: string;
}

export interface ProfileCompleteness {
  score: number;
  sections: Record<string, number>;
  suggestions: string[];
}

export interface ResumeWorthScore {
  score: number;
  breakdown: Record<string, number>;
  label: string;
}

export interface AggregateGapAnalysis {
  most_missing_skills: { skill: string; frequency: number; avg_severity: string }[];
  strongest_areas: { area: string; frequency: number }[];
  recommended_learning: { skill: string; appears_in_jobs: number; total_jobs: number; priority: string }[];
  trending_skills: { skill: string; frequency: number; avg_severity: string }[];
  total_applications_analyzed: number;
}

export interface Language {
  language: string;
  proficiency?: string;
}

export interface ContactInfo {
  email?: string;
  phone?: string;
  location?: string;
  linkedin?: string;
  github?: string;
  website?: string;
}

export interface Skill {
  name: string;
  level?: "beginner" | "intermediate" | "advanced" | "expert";
  years?: number;
  category?: string;
  source?: "resume" | "github" | "linkedin" | "manual";
}

export interface Experience {
  company: string;
  title: string;
  location?: string;
  start_date?: string;
  end_date?: string;
  is_current: boolean;
  description?: string;
  achievements?: string[];
  technologies?: string[];
}

export interface Education {
  institution: string;
  degree: string;
  field?: string;
  start_date?: string;
  end_date?: string;
  gpa?: string;
  achievements?: string[];
}

export interface Certification {
  name: string;
  issuer?: string;
  date?: string;
  expiry?: string;
  credential_id?: string;
  url?: string;
}

export interface Project {
  name: string;
  description?: string;
  role?: string;
  technologies?: string[];
  url?: string;
  achievements?: string[];
}

export interface JobDescription {
  id: string;
  user_id: string;
  title: string;
  company?: string;
  location?: string;
  job_type?: string;
  experience_level?: string;
  salary_range?: string;
  description: string;
  required_skills?: string[];
  preferred_skills?: string[];
  requirements?: string[];
  responsibilities?: string[];
  benefits?: string[];
  company_info?: CompanyInfo;
  created_at: string;
}

export type JobDescriptionCreate = Omit<JobDescription, "id" | "user_id" | "created_at">;

export interface CompanyInfo {
  name?: string;
  industry?: string;
  size?: string;
  description?: string;
  culture?: string;
  values?: string[];
  website?: string;
}

export interface Benchmark {
  id: string;
  job_description_id: string;
  ideal_profile: IdealCandidate;
  ideal_cv: string;
  ideal_cover_letter: string;
  ideal_portfolio?: PortfolioProject[];
  ideal_case_studies?: CaseStudy[];
  ideal_action_plan?: ActionPlan;
  created_at: string;
}

export interface IdealCandidate {
  name: string;
  title: string;
  years_experience: number;
  summary: string;
  key_differentiators: string[];
  career_trajectory: string;
}

export interface PortfolioProject {
  name: string;
  type: string;
  description: string;
  technologies: string[];
  outcomes: string[];
}

export interface CaseStudy {
  title: string;
  company: string;
  problem: {
    description: string;
    impact: string;
  };
  solution: {
    description: string;
  };
  results: {
    metrics: string[];
  };
}

export interface ActionPlan {
  title: string;
  executive_summary: string;
  objectives: string[];
  month_1: MonthPlan;
  month_2: MonthPlan;
  month_3: MonthPlan;
}

export interface MonthPlan {
  theme: string;
  goals: string[];
  activities: Activity[];
  success_metrics: string[];
}

export interface Activity {
  activity: string;
  purpose: string;
  deliverable: string;
}

export interface GapReport {
  id: string;
  user_id: string;
  profile_id: string;
  benchmark_id: string;
  compatibility_score: number;
  skill_score: number;
  experience_score: number;
  education_score: number;
  certification_score: number;
  project_score: number;
  skill_gaps: SkillGap[];
  experience_gaps: ExperienceGap[];
  strengths: Strength[];
  recommendations: Recommendation[];
  summary: GapSummary;
  created_at: string;
}

export interface GapAnalyzeRequest {
  profile_id: string;
  benchmark_id: string;
}

export interface SkillGap {
  skill: string;
  required_level: string;
  current_level?: string;
  gap_severity: string;
  recommendation: string;
  resources?: string[];
}

export interface ExperienceGap {
  area: string;
  required: string;
  current: string;
  recommendation: string;
}

export interface Strength {
  area: string;
  description: string;
  competitive_advantage: string;
  how_to_leverage: string;
}

export interface Recommendation {
  priority: number;
  category: string;
  title: string;
  description: string;
  action_items: string[];
  estimated_effort?: string;
  impact: string;
}

export interface GapSummary {
  compatibility_score: number;
  readiness_level: string;
  top_gaps: string[];
  top_strengths: string[];
}

export interface Roadmap {
  id: string;
  user_id: string;
  gap_report_id: string;
  title: string;
  description?: string;
  milestones: Milestone[];
  learning_path: LearningResource[];
  skill_development: SkillDevelopment[];
  certification_path?: CertificationPath[];
  progress: Record<string, string>;
  status: string;
  created_at: string;
}

export interface Milestone {
  id: string;
  week: number;
  title: string;
  description: string;
  tasks: string[];
  deliverables: string[];
  skills_developed: string[];
  status: string;
}

export interface LearningResource {
  title: string;
  type: string;
  url?: string;
  provider?: string;
  skill_covered: string;
  priority: string;
}

export interface SkillDevelopment {
  skill: string;
  current_level?: string;
  target_level: string;
  timeline: string;
  resources: LearningResource[];
  milestones: string[];
}

export interface CertificationPath {
  certification: string;
  provider: string;
  timeline: string;
  study_plan: StudyStep[];
}

export interface StudyStep {
  week: string;
  focus: string;
  resources: string[];
}

export interface Document {
  id: string;
  user_id: string;
  document_type: string;
  title: string;
  content: string;
  target_job_id?: string;
  target_company?: string;
  version: number;
  status: string;
  is_benchmark: boolean;
  created_at: string;
  updated_at: string;
}

export interface QualityScores {
  impact?: number;
  clarity?: number;
  tone_match?: number;
  completeness?: number;
  ats_readiness?: number;
  readability?: number;
}

export interface FactCheckSummary {
  verified: number;
  enhanced: number;
  fabricated: number;
}

export interface PipelineMeta {
  quality_scores?: QualityScores;
  fact_check?: FactCheckSummary;
  agent_powered?: boolean;
  trace_id?: string;
  total_latency_ms?: number;
}

export interface DocumentGenerateRequest {
  document_type: string;
  profile_id: string;
  job_id: string;
  benchmark_id?: string;
  options?: Record<string, unknown>;
}

export interface RoadmapGenerateRequest {
  gap_report_id: string;
  title?: string;
}

export interface Export {
  id: string;
  user_id: string;
  document_ids: string[];
  format: string;
  filename: string;
  file_url?: string;
  status: string;
  created_at: string;
  completed_at?: string;
  expires_at?: string;
}

export interface DashboardData {
  profiles: number;
  jobs_analyzed: number;
  gap_analyses: number;
  documents_generated: number;
  latest_compatibility_score: number | null;
  active_roadmaps: number;
  summary: {
    has_profile: boolean;
    has_analyzed_job: boolean;
    has_documents: boolean;
    has_roadmap: boolean;
  };
}

// ── Feature types ──────────────────────────────────────────

export interface ATSScan {
  id: string;
  ats_score: number;
  keyword_score: number;
  keyword_match_rate: number;
  readability_score: number;
  format_score: number;
  content_score: number;
  pass_prediction: string;
  matched_keywords: { keyword: string; frequency: number }[];
  missing_keywords: { keyword: string; importance: string; suggestion?: string }[];
  recommendations: { priority: number; impact: string; category: string; text: string }[];
  created_at: string;
  [key: string]: any;
}

export interface InterviewSession {
  id: string;
  job_title: string;
  interview_type: string;
  difficulty: string;
  questions: InterviewQuestion[];
  status: string;
  overall_score?: number;
  overall_feedback?: string;
  feedback?: string;
  created_at: string;
  [key: string]: any;
}

export interface InterviewQuestion {
  id: string;
  text: string;
  question?: string;
  type: string;
  category?: string;
  difficulty: string;
  tips?: string[];
}

export interface InterviewAnswer {
  question_id: string;
  answer: string;
  answer_text?: string;
  score: number;
  feedback?: string;
  star_scores?: Record<string, number>;
  model_answer?: string;
  strengths?: string[];
  improvements?: string[];
  follow_up_suggestion?: string;
}

export interface SalaryAnalysis {
  market_range?: { low: number; median: number; high: number };
  market_data?: { percentile_25: number; median: number; percentile_75: number; percentile_90: number; sample_size: number };
  salary_range?: { low: number; mid: number; high: number; target?: number; recommended_min?: number; recommended_max?: number; reasoning?: string; currency: string };
  percentile?: number;
  negotiation_scripts?: any[];
  talking_points?: string[];
  comparables?: { company: string; range: string; source?: string }[];
  counter_offers?: any[];
  [key: string]: any;
}

export interface CareerSnapshot {
  id: string;
  date: string;
  snapshot_date: string;
  overall_score: number;
  technical_score?: number;
  experience_score?: number;
  education_score?: number;
  avg_ats_score?: number;
  skills_count: number;
  experience_years: number;
  certifications_count: number;
  compatibility_score?: number;
  highlights?: string[];
  [key: string]: any;
}

export interface LearningChallenge {
  id: string;
  question: string;
  options: string[];
  correct_answer?: string;
  explanation?: string;
  difficulty: string;
  topic: string;
  challenge_type?: string;
  skill?: string;
  points_earned?: number;
  [key: string]: any;
}

export interface LearningStreak {
  current_streak: number;
  longest_streak: number;
  total_completed: number;
  today_completed: number;
  total_points?: number;
  total_challenges?: number;
  correct_challenges?: number;
  level?: number;
  skills_mastered?: string[];
}

export interface DocVariant {
  id: string;
  tone: string;
  content: string;
  score?: number;
  label?: string;
  ats_score?: number;
  readability_score?: number;
  [key: string]: any;
}

export interface JobAlert {
  id: string;
  keywords: string[];
  location?: string;
  min_salary?: number;
  max_salary?: number;
  is_active: boolean;
  created_at: string;
}

export interface JobMatch {
  id: string;
  alert_id: string;
  title: string;
  company: string;
  location?: string;
  salary_range?: string;
  url?: string;
  source_url?: string;
  match_score?: number;
  match_reasons?: string[];
  description?: string;
  source?: string;
  status: string;
  created_at: string;
}

export interface APIKey {
  id: string;
  name: string;
  prefix: string;
  key_prefix?: string;
  created_at: string;
  last_used?: string;
  last_used_at?: string;
  is_active: boolean;
}

export interface ReviewSession {
  id: string;
  document_id: string;
  token: string;
  reviewer_email?: string;
  status: string;
  document_content?: string;
  document_title?: string;
  document_type?: string;
  expires_at: string;
  created_at: string;
}

export interface ReviewComment {
  id: string;
  session_id: string;
  reviewer_name: string;
  comment_text: string;
  section?: string;
  sentiment?: string;
  created_at: string;
}
