/**
 * Application Domain Types
 *
 * Type-safe definitions for job application workflow.
 */

export interface JobDetails {
  id: string;
  title: string;
  company: string;
  location?: string;
  description?: string;
  salaryRange?: string;
  url?: string;
  postedDate?: string;
  companySize?: string;
  industry?: string;
}

export interface ApplicationDocument {
  id: string;
  type: "cv" | "cover_letter" | "roadmap" | "portfolio";
  title: string;
  content: string;
  status: "generating" | "complete" | "error";
  progress: number;
  createdAt: string;
  updatedAt: string;
  downloadUrl?: string;
}

export interface Application {
  id: string;
  userId: string;
  resumeId: string;
  jobDetails: JobDetails;
  documents: ApplicationDocument[];
  status: "draft" | "generating" | "review" | "ready" | "sent";
  atsScore?: number;
  gapAnalysis?: GapAnalysis;
  createdAt: string;
  updatedAt: string;
  sentAt?: string;
}

export interface GapAnalysis {
  matchingSkills: string[];
  missingSkills: string[];
  skillGaps: SkillGap[];
  experienceMatch: number;
  overallMatch: number;
  recommendations: string[];
}

export interface SkillGap {
  skill: string;
  required: "must" | "preferred";
  userHas: boolean;
  evidence?: string;
}

export interface GenerationProgress {
  phase: string;
  progress: number;
  message: string;
  documentType?: string;
}

export interface CreateApplicationRequest {
  resumeId: string;
  jobTitle: string;
  company: string;
  location?: string;
  jobDescription?: string;
  jobUrl?: string;
}

export interface GenerationRequest {
  applicationId: string;
  documentTypes: ("cv" | "cover_letter" | "roadmap")[];
  tone?: "professional" | "enthusiastic" | "formal" | "casual";
  focus?: string[];
}
