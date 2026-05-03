/**
 * Resume API Service
 *
 * Type-safe API client for resume operations.
 */

import api from "@/lib/api";
import type {
  Resume,
  ResumeUploadResult,
  ResumeOptimizationRequest,
  OptimizationSuggestion,
  ATSScore,
} from "../types/resume";

export interface UploadResumeRequest {
  file: File;
  onProgress?: (progress: number) => void;
}

export interface CreateResumeRequest {
  title: string;
  content: string;
}

export interface UpdateResumeRequest {
  resumeId: string;
  updates: Partial<Resume>;
}

export const resumeApi = {
  /**
   * Upload and parse a resume file.
   */
  async upload({ file }: UploadResumeRequest): Promise<ResumeUploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    // Use native fetch for FormData (not JSON)
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/resume/upload`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }

    return response.json();
  },

  /**
   * Get a resume by ID.
   */
  async getById(resumeId: string): Promise<Resume> {
    return api.request<Resume>(`/resume/${resumeId}`);
  },

  /**
   * Get all resumes for the current user.
   */
  async getAll(): Promise<Resume[]> {
    return api.request<Resume[]>("/resume");
  },

  /**
   * Create a new resume from scratch.
   */
  async create(data: CreateResumeRequest): Promise<Resume> {
    return api.request<Resume>("/resume", { method: "POST", body: data });
  },

  /**
   * Update a resume.
   */
  async update({ resumeId, updates }: UpdateResumeRequest): Promise<Resume> {
    return api.request<Resume>(`/resume/${resumeId}`, { method: "PUT", body: updates });
  },

  /**
   * Delete a resume.
   */
  async delete(resumeId: string): Promise<void> {
    await api.request<void>(`/resume/${resumeId}`, { method: "DELETE" });
  },

  /**
   * Get ATS score for a resume.
   */
  async getATSScore(resumeId: string): Promise<ATSScore> {
    return api.request<ATSScore>(`/resume/${resumeId}/ats-score`);
  },

  /**
   * Get optimization suggestions for a resume.
   */
  async getSuggestions(resumeId: string): Promise<OptimizationSuggestion[]> {
    return api.request<OptimizationSuggestion[]>(`/resume/${resumeId}/suggestions`);
  },

  /**
   * Optimize a resume for a target job.
   */
  async optimize(request: ResumeOptimizationRequest): Promise<Resume> {
    return api.request<Resume>("/resume/optimize", { method: "POST", body: request });
  },

  /**
   * Apply an optimization suggestion.
   */
  async applySuggestion(resumeId: string, suggestionId: string): Promise<Resume> {
    return api.request<Resume>(`/resume/${resumeId}/suggestions/${suggestionId}/apply`, {
      method: "POST",
    });
  },

  /**
   * Export resume to PDF.
   */
  async exportToPDF(resumeId: string): Promise<Blob> {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/resume/${resumeId}/export/pdf`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
    });
    return response.blob();
  },

  /**
   * Export resume to Word.
   */
  async exportToWord(resumeId: string): Promise<Blob> {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/resume/${resumeId}/export/docx`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
      },
    });
    return response.blob();
  },
};
