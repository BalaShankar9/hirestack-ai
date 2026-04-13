/**
 * HireStack AI — User Flow Modules
 *
 * Reusable flow functions composed into scenarios.
 * Each flow simulates a real user journey.
 */

import { group, sleep } from "k6";
import {
  BASE_URL,
  authGet,
  authPost,
  authPut,
  authDel,
  checkOk,
  checkStatus,
  checkJson,
} from "../config.js";
import http from "k6/http";

// ---------------------------------------------------------------------------
// 1. Health check (unauthenticated)
// ---------------------------------------------------------------------------
export function flowHealthCheck() {
  group("Health Check", () => {
    const res = http.get(`${BASE_URL}/health`, {
      tags: { name: "/health", type: "health" },
    });
    checkOk(res, "health endpoint OK");
  });
}

// ---------------------------------------------------------------------------
// 2. Auth & Profile — login sync, fetch profile list, get primary
// ---------------------------------------------------------------------------
export function flowAuthAndProfile() {
  group("Auth & Profile", () => {
    // Sync user (simulates post-login)
    const syncRes = authPost("/api/auth/sync", {});
    checkOk(syncRes, "auth sync OK");
    sleep(0.3);

    // Get current user
    const meRes = authGet("/api/auth/me");
    checkOk(meRes, "auth/me OK");
    sleep(0.2);

    // List profiles
    const profilesRes = authGet("/api/profile");
    checkOk(profilesRes, "list profiles OK");
    checkJson(profilesRes);
    sleep(0.2);

    // Get primary profile
    const primaryRes = authGet("/api/profile/primary");
    // 200 if exists, 404 if no primary yet — both are acceptable
    checkStatus(primaryRes, primaryRes.status === 200 ? 200 : 404, "primary profile");
  });
}

// ---------------------------------------------------------------------------
// 3. Dashboard reads — the most common authenticated page load
// ---------------------------------------------------------------------------
export function flowDashboard() {
  group("Dashboard", () => {
    // All 3 calls a dashboard page makes on mount
    const dashboard = authGet("/api/analytics/dashboard");
    checkOk(dashboard, "analytics dashboard OK");

    const activity = authGet("/api/analytics/activity");
    checkOk(activity, "analytics activity OK");

    const progress = authGet("/api/analytics/progress");
    checkOk(progress, "analytics progress OK");
    sleep(0.5);
  });
}

// ---------------------------------------------------------------------------
// 4. Job CRUD — create job, parse JD, list, get, delete
// ---------------------------------------------------------------------------
export function flowJobCrud() {
  group("Job CRUD", () => {
    // Create job
    const createRes = authPost("/api/jobs", {
      title: `K6 Load Test Engineer - ${Date.now()}`,
      company: "HireStack Test Corp",
      description: "We are looking for a senior backend engineer with experience in Python, FastAPI, and distributed systems.",
      url: "https://example.com/jobs/test",
      status: "active",
    });
    checkOk(createRes, "job create OK");

    let jobId = null;
    try {
      const body = createRes.json();
      jobId = body.id || body.job_id;
    } catch (_) {}

    sleep(0.5);

    // List jobs
    const listRes = authGet("/api/jobs");
    checkOk(listRes, "job list OK");

    if (jobId) {
      // Get job
      const getRes = authGet(`/api/jobs/${jobId}`);
      checkOk(getRes, "job get OK");
      sleep(0.3);

      // Parse JD
      const parseRes = authPost(`/api/jobs/${jobId}/parse`, {}, "ai");
      checkOk(parseRes, "job parse OK");
      sleep(0.5);

      // Delete job (cleanup)
      const delRes = authDel(`/api/jobs/${jobId}`);
      checkOk(delRes, "job delete OK");
    }
  });
}

// ---------------------------------------------------------------------------
// 5. Document Library — list, get summary
// ---------------------------------------------------------------------------
export function flowDocumentLibrary() {
  group("Document Library", () => {
    const libRes = authGet("/api/documents/library");
    checkOk(libRes, "doc library OK");

    const sumRes = authGet("/api/documents/library/summary");
    checkOk(sumRes, "doc library summary OK");
    sleep(0.3);
  });
}

// ---------------------------------------------------------------------------
// 6. Career Analytics — timeline, portfolio, snapshot
// ---------------------------------------------------------------------------
export function flowCareerAnalytics() {
  group("Career Analytics", () => {
    const timeline = authGet("/api/career/timeline");
    checkOk(timeline, "career timeline OK");

    const portfolio = authGet("/api/career/portfolio");
    checkOk(portfolio, "career portfolio OK");
    sleep(0.3);
  });
}

// ---------------------------------------------------------------------------
// 7. Learning Hub — streak, today's challenges, history
// ---------------------------------------------------------------------------
export function flowLearning() {
  group("Learning Hub", () => {
    const streak = authGet("/api/learning/streak");
    checkOk(streak, "learning streak OK");

    const today = authGet("/api/learning/today");
    checkOk(today, "learning today OK");

    const history = authGet("/api/learning/history");
    checkOk(history, "learning history OK");
    sleep(0.3);
  });
}

// ---------------------------------------------------------------------------
// 8. Candidates pipeline — list, stats
// ---------------------------------------------------------------------------
export function flowCandidates() {
  group("Candidates Pipeline", () => {
    const listRes = authGet("/api/candidates");
    checkOk(listRes, "candidates list OK");

    const statsRes = authGet("/api/candidates/stats");
    checkOk(statsRes, "candidates stats OK");
    sleep(0.3);
  });
}

// ---------------------------------------------------------------------------
// 9. Salary analysis — list recent
// ---------------------------------------------------------------------------
export function flowSalary() {
  group("Salary Coach", () => {
    const listRes = authGet("/api/salary/");
    checkOk(listRes, "salary list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 10. Billing status check
// ---------------------------------------------------------------------------
export function flowBilling() {
  group("Billing", () => {
    const res = authGet("/api/billing/status");
    checkOk(res, "billing status OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 11. Job Sync — alerts and matches
// ---------------------------------------------------------------------------
export function flowJobSync() {
  group("Job Sync", () => {
    const alerts = authGet("/api/job-sync/alerts");
    checkOk(alerts, "job sync alerts OK");

    const matches = authGet("/api/job-sync/matches");
    checkOk(matches, "job sync matches OK");
    sleep(0.3);
  });
}

// ---------------------------------------------------------------------------
// 12. Gap Reports — list
// ---------------------------------------------------------------------------
export function flowGapReports() {
  group("Gap Reports", () => {
    const listRes = authGet("/api/gaps");
    checkOk(listRes, "gap reports list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 13. Interview Sessions — list
// ---------------------------------------------------------------------------
export function flowInterviewSessions() {
  group("Interview Sessions", () => {
    const listRes = authGet("/api/interview/sessions");
    checkOk(listRes, "interview sessions list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 14. ATS Scans — list
// ---------------------------------------------------------------------------
export function flowAtsScans() {
  group("ATS Scans", () => {
    const listRes = authGet("/api/ats");
    checkOk(listRes, "ats scans list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 15. Organization — list
// ---------------------------------------------------------------------------
export function flowOrgs() {
  group("Organizations", () => {
    const listRes = authGet("/api/orgs");
    checkOk(listRes, "orgs list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 16. Reviews — list
// ---------------------------------------------------------------------------
export function flowReviews() {
  group("Reviews", () => {
    const listRes = authGet("/api/review/");
    checkOk(listRes, "reviews list OK");
    sleep(0.2);
  });
}

// ---------------------------------------------------------------------------
// 17. Heavy AI flow — full pipeline generation (only for stress/spike)
// ---------------------------------------------------------------------------
export function flowAiGeneration() {
  group("AI Generation (Pipeline)", () => {
    // This hits the synchronous generation endpoint
    // Only use sparingly — each call invokes the full AI pipeline
    const res = authPost(
      "/api/generate/pipeline",
      {
        profile_id: "test",
        job_id: "test",
        document_types: ["cv"],
      },
      "ai"
    );
    // 200 = success, 402 = billing limit, 422 = validation error
    // All are acceptable under load — we're measuring latency, not correctness
    checkStatus(
      res,
      res.status >= 200 && res.status < 500 ? res.status : 200,
      "AI pipeline non-5xx"
    );
    sleep(1);
  });
}
