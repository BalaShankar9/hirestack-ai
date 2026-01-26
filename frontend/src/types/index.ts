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
  is_primary: boolean;
  created_at: string;
  updated_at: string;
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

export interface DocumentGenerateRequest {
  document_type: string;
  profile_id: string;
  job_id: string;
  benchmark_id?: string;
  options?: Record<string, any>;
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
