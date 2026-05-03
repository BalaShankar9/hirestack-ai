/**
 * Application API Service
 *
 * Type-safe API client for application operations.
 */

import api from "@/lib/api";
import type {
  Application,
  CreateApplicationRequest,
  GenerationRequest,
  GenerationProgress,
} from "../types/application";

export const applicationApi = {
  /**
   * Create a new job application.
   */
  async create(data: CreateApplicationRequest): Promise<Application> {
    return api.request<Application>("/applications", { method: "POST", body: data });
  },

  /**
   * Get an application by ID.
   */
  async getById(applicationId: string): Promise<Application> {
    return api.request<Application>(`/applications/${applicationId}`);
  },

  /**
   * Get all applications for the current user.
   */
  async getAll(): Promise<Application[]> {
    return api.request<Application[]>("/applications");
  },

  /**
   * Update an application.
   */
  async update(
    applicationId: string,
    updates: Partial<Application>
  ): Promise<Application> {
    return api.request<Application>(`/applications/${applicationId}`, {
      method: "PUT",
      body: updates,
    });
  },

  /**
   * Delete an application.
   */
  async delete(applicationId: string): Promise<void> {
    await api.request<void>(`/applications/${applicationId}`, { method: "DELETE" });
  },

  /**
   * Generate documents for an application.
   */
  async generate(applicationId: string, request: GenerationRequest): Promise<void> {
    await api.request<void>(`/applications/${applicationId}/generate`, {
      method: "POST",
      body: request,
    });
  },

  /**
   * Stream generation progress.
   * Returns a ReadableStream for SSE consumption.
   */
  async streamProgress(applicationId: string): Promise<ReadableStream<Uint8Array>> {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || ""}/api/applications/${applicationId}/progress`,
      {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
          Accept: "text/event-stream",
        },
      }
    );
    return response.body!;
  },

  /**
   * Mark application as sent.
   */
  async markAsSent(applicationId: string): Promise<Application> {
    return api.request<Application>(`/applications/${applicationId}/send`, {
      method: "POST",
    });
  },

  /**
   * Duplicate an application for a new job.
   */
  async duplicate(applicationId: string, newJobDetails: {
    jobTitle: string;
    company: string;
  }): Promise<Application> {
    return api.request<Application>(`/applications/${applicationId}/duplicate`, {
      method: "POST",
      body: newJobDetails,
    });
  },
};
