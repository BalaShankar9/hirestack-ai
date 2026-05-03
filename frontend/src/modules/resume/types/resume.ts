/**
 * Resume Domain Types
 *
 * Type-safe definitions for resume-related data structures.
 */

export interface Skill {
  id: string;
  name: string;
  level?: "beginner" | "intermediate" | "advanced" | "expert";
  category?: string;
  yearsOfExperience?: number;
}

export interface Experience {
  id: string;
  company: string;
  title: string;
  location?: string;
  startDate: string;
  endDate?: string;
  current: boolean;
  description: string;
  achievements: string[];
}

export interface Education {
  id: string;
  institution: string;
  degree: string;
  fieldOfStudy?: string;
  location?: string;
  startDate: string;
  endDate?: string;
  gpa?: string;
}

export interface ContactInfo {
  email: string;
  phone?: string;
  website?: string;
  linkedin?: string;
  github?: string;
  location?: string;
}

export interface Resume {
  id: string;
  userId: string;
  title: string;
  contact: ContactInfo;
  summary?: string;
  skills: Skill[];
  experiences: Experience[];
  education: Education[];
  certifications?: string[];
  projects?: Project[];
  createdAt: string;
  updatedAt: string;
  parsed?: boolean;
  atsScore?: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  url?: string;
  technologies?: string[];
}

export interface ATSScore {
  overall: number;
  readability: number;
  keywordMatch: number;
  formatting: number;
  suggestions: string[];
}

export interface OptimizationSuggestion {
  id: string;
  type: "skill" | "experience" | "formatting" | "keyword";
  section?: string;
  original?: string;
  suggestion: string;
  reason: string;
  priority: "high" | "medium" | "low";
  applied: boolean;
}

export interface ResumeUploadResult {
  resumeId: string;
  parsedResume: Resume;
  atsScore: ATSScore;
  suggestions: OptimizationSuggestion[];
}

export interface ResumeOptimizationRequest {
  resumeId: string;
  targetJobTitle?: string;
  targetCompany?: string;
  focusAreas?: ("skills" | "experience" | "keywords")[];
}
