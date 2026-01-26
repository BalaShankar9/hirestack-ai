import type {
  DocumentGenerateRequest,
  GapAnalyzeRequest,
  JobDescriptionCreate,
  Profile,
  RoadmapGenerateRequest,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: any;
  headers?: Record<string, string>;
  token?: string;
}

class APIClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T = any>(
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

    const response = await fetch(`${this.baseUrl}/api${endpoint}`, config);

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
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

  // Auth
  async login(email: string, password: string) {
    return this.request("/auth/login", {
      method: "POST",
      body: { email, password },
    });
  }

  async register(email: string, password: string, fullName?: string) {
    return this.request("/auth/register", {
      method: "POST",
      body: { email, password, full_name: fullName },
    });
  }

  async getMe() {
    return this.request("/auth/me");
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
    upload: async (file: File, isPrimary: boolean = true) =>
      this.uploadResume(file, isPrimary),
    update: async (data: Partial<Profile>) => {
      if (!data.id) {
        throw new Error("Profile id is required");
      }
      return this.request(`/profile/${data.id}`, { method: "PUT", body: data });
    },
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
}

export const api = new APIClient(API_URL);
export default api;
