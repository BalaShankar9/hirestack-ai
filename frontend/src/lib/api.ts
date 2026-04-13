/**
 * DEPRECATION NOTICE: This API client file is kept for backward compatibility.
 * The frontend primarily uses Supabase directly via the Firestore operations in @/lib/firestore/ops.
 * New features should use the Firestore/Supabase client instead of this REST API client.
 * This file may be removed in a future version.
 */

import type {
  DocumentGenerateRequest,
  GapAnalyzeRequest,
  JobDescriptionCreate,
  Profile,
  RoadmapGenerateRequest,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? "" : "http://127.0.0.1:8000");
if (typeof window !== "undefined" && !process.env.NEXT_PUBLIC_API_URL) {
  console.error("[HireStack] NEXT_PUBLIC_API_URL is not set — API calls will fail in production.");
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: any;
  headers?: Record<string, string>;
  token?: string;
}

class APIClient {
  private baseUrl: string;
  private token: string | null = null;
  private static readonly MAX_RETRIES = 3;
  private static readonly NON_RETRYABLE = new Set([400, 401, 402, 403, 404, 409, 422]);

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  async request<T = any>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { method = "GET", body, headers = {}, token } = options;

    const authToken = token || this.token;

    const config: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(authToken && { Authorization: `Bearer ${authToken}` }),
        ...headers,
      },
    };

    if (body && method !== "GET") {
      config.body = JSON.stringify(body);
    }

    let lastError: Error | null = null;
    for (let attempt = 1; attempt <= APIClient.MAX_RETRIES; attempt++) {
      let response: Response;
      try {
        response = await fetch(`${this.baseUrl}/api${endpoint}`, config);
      } catch (networkErr) {
        // Network-level failure (offline, DNS, CORS preflight) — retryable
        lastError = networkErr instanceof Error ? networkErr : new Error("Network error");
        if (attempt < APIClient.MAX_RETRIES) {
          await new Promise((r) => setTimeout(r, attempt * 2000));
          continue;
        }
        throw lastError;
      }

      if (response.ok) {
        if (response.status === 204) return {} as T;
        return response.json();
      }

      // Non-retryable status codes — fail immediately
      if (APIClient.NON_RETRYABLE.has(response.status)) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP error! status: ${response.status}`);
      }

      // Retryable (503, 429, 5xx) — respect Retry-After header
      const retryAfter = response.headers.get("Retry-After");
      const delayMs = retryAfter && Number.isFinite(Number(retryAfter))
        ? Number(retryAfter) * 1000
        : attempt * 2000;

      const error = await response.json().catch(() => ({}));
      lastError = new Error(error.detail || `HTTP error! status: ${response.status}`);

      if (attempt < APIClient.MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }

    throw lastError!;
  }

  async uploadFile(
    endpoint: string,
    file: File,
    additionalData?: Record<string, string>,
    token?: string
  ): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);

    if (additionalData) {
      Object.entries(additionalData).forEach(([key, value]) => {
        formData.append(key, value);
      });
    }

    const authToken = token || this.token;

    const response = await fetch(`${this.baseUrl}/api${endpoint}`, {
      method: "POST",
      headers: {
        ...(authToken && { Authorization: `Bearer ${authToken}` }),
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Upload failed`);
    }

    return response.json();
  }

  // Profile
  async uploadResume(file: File, isPrimary: boolean = false) {
    return this.uploadFile("/profile/upload", file, {
      is_primary: isPrimary.toString(),
    });
  }

  async getProfiles() {
    return this.request("/profile");
  }

  async getPrimaryProfile() {
    return this.request("/profile/primary");
  }

  async getProfile(id: string) {
    return this.request(`/profile/${id}`);
  }

  // Jobs
  async createJob(data: any) {
    return this.request("/jobs", { method: "POST", body: data });
  }

  async getJobs() {
    return this.request("/jobs");
  }

  async getJob(id: string) {
    return this.request(`/jobs/${id}`);
  }

  // Benchmark
  async generateBenchmark(jobId: string) {
    return this.request("/benchmark/generate", {
      method: "POST",
      body: { job_description_id: jobId },
    });
  }

  async getBenchmark(id: string) {
    return this.request(`/benchmark/${id}`);
  }

  async getBenchmarkForJob(jobId: string) {
    return this.request(`/benchmark/job/${jobId}`);
  }

  // Gap Analysis
  async analyzeGaps(profileId: string, benchmarkId: string) {
    return this.request("/gaps/analyze", {
      method: "POST",
      body: { profile_id: profileId, benchmark_id: benchmarkId },
    });
  }

  async getGapReports() {
    return this.request("/gaps");
  }

  async getGapReport(id: string) {
    return this.request(`/gaps/${id}`);
  }

  // Roadmap
  async generateRoadmap(gapReportId: string, title?: string) {
    return this.request("/consultant/roadmap", {
      method: "POST",
      body: { gap_report_id: gapReportId, title },
    });
  }

  async getRoadmaps() {
    return this.request("/consultant/roadmaps");
  }

  async getRoadmap(id: string) {
    return this.request(`/consultant/roadmap/${id}`);
  }

  // Documents
  async generateDocument(data: any) {
    return this.request("/builder/generate", { method: "POST", body: data });
  }

  async generateAllDocuments(profileId: string, jobId: string) {
    return this.request(
      `/builder/generate-all?profile_id=${profileId}&job_id=${jobId}`,
      { method: "POST" }
    );
  }

  async getDocuments(type?: string) {
    const query = type ? `?document_type=${type}` : "";
    return this.request(`/builder/documents${query}`);
  }

  async getDocument(id: string) {
    return this.request(`/builder/documents/${id}`);
  }

  async updateDocument(id: string, data: any) {
    return this.request(`/builder/documents/${id}`, {
      method: "PUT",
      body: data,
    });
  }

  // Export
  async createExport(data: any) {
    return this.request("/export", { method: "POST", body: data });
  }

  async getExports() {
    return this.request("/export");
  }

  async downloadExport(id: string) {
    return `${this.baseUrl}/api/export/${id}/download`;
  }

  // Analytics
  async getDashboard() {
    return this.request("/analytics/dashboard");
  }

  async getProgress() {
    return this.request("/analytics/progress");
  }

  // Resource-style API helpers (used by hooks/)
  profile = {
    get: async () => this.getPrimaryProfile(),
    getById: async (id: string) => this.getProfile(id),
    list: async () => this.getProfiles(),
    upload: async (file: File, isPrimary: boolean = true) =>
      this.uploadResume(file, isPrimary),
    update: async (data: Partial<Profile>) => {
      if (!data.id) {
        throw new Error("Profile id is required");
      }
      return this.request(`/profile/${data.id}`, { method: "PUT", body: data });
    },
    delete: async (id: string) =>
      this.request(`/profile/${id}`, { method: "DELETE" }),
    setPrimary: async (id: string) =>
      this.request(`/profile/${id}/set-primary`, { method: "POST" }),
    reparse: async (id: string) =>
      this.request(`/profile/${id}/reparse`, { method: "POST" }),
    updateSocialLinks: async (id: string, links: { linkedin?: string; github?: string; website?: string; twitter?: string; other?: string }) =>
      this.request(`/profile/${id}/social-links`, { method: "PUT", body: links }),
    connectSocial: async (id: string, platform: string, url: string) =>
      this.request(`/profile/${id}/connect-social`, { method: "POST", body: { platform, url } }),
    augmentSkills: async (id: string) =>
      this.request(`/profile/${id}/augment-skills`, { method: "POST" }),
    generateUniversalDocs: async (id: string) =>
      this.request(`/profile/${id}/universal-documents`, { method: "POST" }),
    completeness: async () =>
      this.request("/profile/intelligence/completeness"),
    resumeWorth: async () =>
      this.request("/profile/intelligence/resume-worth"),
    aggregateGaps: async () =>
      this.request("/profile/intelligence/aggregate-gaps"),
    marketIntelligence: async (forceRefresh = false) =>
      this.request(`/profile/intelligence/market?force_refresh=${forceRefresh}`),
    syncedEvidence: async () =>
      this.request("/profile/evidence/synced"),
    syncEvidence: async (id: string) =>
      this.request(`/profile/${id}/sync-evidence`, { method: "POST" }),
  };

  jobs = {
    list: async () => this.getJobs(),
    get: async (id: string) => this.getJob(id),
    create: async (data: JobDescriptionCreate) => this.createJob(data),
    delete: async (id: string) =>
      this.request(`/jobs/${id}`, { method: "DELETE" }),
    parse: async (id: string) =>
      this.request(`/jobs/${id}/parse`, { method: "POST" }),
  };

  benchmark = {
    get: async (id: string) => this.getBenchmark(id),
    getByJob: async (jobId: string) => this.getBenchmarkForJob(jobId),
    generate: async (jobDescriptionId: string) =>
      this.generateBenchmark(jobDescriptionId),
    regenerate: async (benchmarkId: string) =>
      this.request(`/benchmark/${benchmarkId}/regenerate`, { method: "POST" }),
    delete: async (benchmarkId: string) =>
      this.request(`/benchmark/${benchmarkId}`, { method: "DELETE" }),
  };

  gaps = {
    list: async () => this.getGapReports(),
    get: async (reportId: string) => this.getGapReport(reportId),
    analyze: async (data: GapAnalyzeRequest) =>
      this.request("/gaps/analyze", { method: "POST", body: data }),
    refresh: async (reportId: string) =>
      this.request(`/gaps/${reportId}/refresh`, { method: "POST" }),
    delete: async (reportId: string) =>
      this.request(`/gaps/${reportId}`, { method: "DELETE" }),
  };

  consultant = {
    listRoadmaps: async () => this.getRoadmaps(),
    getRoadmap: async (roadmapId: string) => this.getRoadmap(roadmapId),
    generateRoadmap: async (data: RoadmapGenerateRequest) =>
      this.generateRoadmap(data.gap_report_id, data.title),
    deleteRoadmap: async (roadmapId: string) =>
      this.request(`/consultant/roadmap/${roadmapId}`, { method: "DELETE" }),
    askCoach: async (appId: string, question: string) =>
      this.request("/consultant/coach", { method: "POST", body: { app_id: appId, question } }),
  };

  builder = {
    list: async () => this.getDocuments(),
    get: async (documentId: string) => this.getDocument(documentId),
    generate: async (data: DocumentGenerateRequest) => this.generateDocument(data),
    update: async (id: string, content: string) =>
      this.updateDocument(id, { content }),
    delete: async (documentId: string) =>
      this.request(`/builder/documents/${documentId}`, { method: "DELETE" }),
  };

  // ── Feature API methods ──────────────────────────────────────────

  ats = {
    scan: async (data: { document_content: string; document_type?: string; job_title?: string; company?: string; jd_text?: string }) =>
      this.request("/ats/scan", { method: "POST", body: data }),
    get: async (scanId: string) => this.request(`/ats/${scanId}`),
  };

  interview = {
    start: async (data: { job_title: string; interview_type?: string; difficulty?: string; question_count?: number; profile_summary?: string; skills_summary?: string }) =>
      this.request("/interview/sessions", { method: "POST", body: data }),
    submitAnswer: async (sessionId: string, data: { question_id: string; answer: string }) =>
      this.request(`/interview/sessions/${sessionId}/answers`, { method: "POST", body: data }),
    complete: async (sessionId: string) =>
      this.request(`/interview/sessions/${sessionId}/complete`, { method: "POST" }),
    get: async (sessionId: string) => this.request(`/interview/sessions/${sessionId}`),
  };

  salary = {
    analyze: async (data: { job_title: string; company?: string; location?: string; years_experience?: number; current_salary?: number; skills_summary?: string }) =>
      this.request("/salary/analyze", { method: "POST", body: data }),
  };

  career = {
    timeline: async () => this.request("/career/timeline"),
    portfolio: async () => this.request("/career/portfolio"),
    snapshot: async () => this.request("/career/snapshot", { method: "POST" }),
    // Outcome tracking — closed-loop quality learning
    recordOutcome: async (data: { application_id: string; signal_type: string; signal_data?: Record<string, unknown> }) =>
      this.request("/career/outcomes", { method: "POST", body: data }),
    conversionFunnel: async () => this.request("/career/outcomes/funnel"),
    strategyEffectiveness: async () => this.request("/career/outcomes/effectiveness"),
    // Pipeline telemetry — cost and quality dashboards
    telemetrySummary: async (days = 30) => this.request(`/career/telemetry/summary?days=${days}`),
    telemetryTrend: async (pipelineName: string, limit = 20) =>
      this.request(`/career/telemetry/trend/${encodeURIComponent(pipelineName)}?limit=${limit}`),
    // Production replay — reconstruct pipeline state from event log
    replayState: async (jobId: string) => this.request(`/career/replay/${jobId}`),
    // Self-tuning engine — optimal pipeline config recommendation
    tuningRecommendation: async () => this.request("/career/tuning/recommendation"),
    // Interview prediction — statistical likelihood scoring
    predictInterview: async (applicationId: string) =>
      this.request(`/career/predict/${encodeURIComponent(applicationId)}`),
    // Pipeline health — regression and anomaly detection
    pipelineHealth: async () => this.request("/career/telemetry/health"),
    // Evidence graph — canonical nodes + contradictions
    evidenceGraph: async () => this.request("/career/evidence-graph"),
    // Autonomous career monitor — proactive alerts
    triggerScan: async () => this.request("/career/monitor/scan", { method: "POST" }),
    alerts: async (limit = 20) => this.request(`/career/alerts?limit=${limit}`),
    alertSummary: async () => this.request("/career/alerts/summary"),
    dismissAlert: async (alertId: string) =>
      this.request(`/career/alerts/${encodeURIComponent(alertId)}/dismiss`, { method: "POST" }),
    markAlertRead: async (alertId: string) =>
      this.request(`/career/alerts/${encodeURIComponent(alertId)}/read`, { method: "POST" }),
    // Document evolution — semantic diff tracking
    analyzeEvolution: async (data: {
      document_id: string; old_content: string; new_content: string;
      version_from: number; version_to: number;
      application_id?: string; target_keywords?: string[];
    }) => this.request("/career/document-evolution", { method: "POST", body: data }),
    evolutionTimeline: async (documentId?: string, applicationId?: string, limit = 20) => {
      const params = new URLSearchParams();
      if (documentId) params.set("document_id", documentId);
      if (applicationId) params.set("application_id", applicationId);
      params.set("limit", String(limit));
      return this.request(`/career/document-evolution/timeline?${params}`);
    },
    improvementTrend: async (limit = 30) =>
      this.request(`/career/document-evolution/trend?limit=${limit}`),
    // Predictive career forecaster — enhanced predictions
    predictOffer: async (applicationId: string) =>
      this.request(`/career/predict/offer/${encodeURIComponent(applicationId)}`),
    careerMomentum: async () => this.request("/career/momentum"),
  };

  learning = {
    getStreak: async () => this.request("/learning/streak"),
    getToday: async () => this.request("/learning/today"),
    generate: async (data?: { topic?: string; difficulty?: string; skills?: string[] }) =>
      this.request("/learning/generate", { method: "POST", body: data ?? {} }),
    submitAnswer: async (challengeId: string, data: string | { answer: string }) =>
      this.request(`/learning/${challengeId}/answer`, {
        method: "POST",
        body: typeof data === "string" ? { answer: data } : data,
      }),
  };

  variants = {
    generate: async (data: { original_content?: string; application_id?: string; document_type: string; job_title?: string; tones?: string[] }) =>
      this.request("/variants/generate", { method: "POST", body: data }),
    select: async (variantId: string) =>
      this.request(`/variants/${variantId}/select`, { method: "POST" }),
  };

  jobSync = {
    getAlerts: async () => this.request("/job-sync/alerts"),
    getMatches: async (alertId?: string) =>
      this.request(`/job-sync/matches${alertId ? `?alert_id=${alertId}` : ""}`),
    createAlert: async (data: { keywords: string[]; location?: string; min_salary?: number; max_salary?: number }) =>
      this.request("/job-sync/match", { method: "POST", body: data }),
    deleteAlert: async (alertId: string) =>
      this.request(`/job-sync/alerts`, { method: "DELETE", body: { alert_id: alertId } }),
    updateMatchStatus: async (matchId: string, status: string) =>
      this.request(`/job-sync/matches/${matchId}/status`, { method: "PUT", body: { status } }),
  };

  apiKeys = {
    list: async () => this.request("/api-keys/keys"),
    usage: async () => this.request("/api-keys/usage"),
    create: async (data: { name: string }) =>
      this.request("/api-keys/keys", { method: "POST", body: data }),
    revoke: async (keyId: string) =>
      this.request(`/api-keys/keys/${keyId}`, { method: "DELETE" }),
  };

  review = {
    getByToken: async (token: string) => this.request(`/review/${token}`),
    getComments: async (sessionId: string) => this.request(`/review/${sessionId}/comments`),
    addComment: async (sessionId: string, data: { reviewer_name: string; comment_text: string; section?: string }) =>
      this.request(`/review/${sessionId}/comments`, { method: "POST", body: data }),
  };
}

export const api = new APIClient(API_URL);
export default api;
