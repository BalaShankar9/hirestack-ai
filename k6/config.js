/**
 * HireStack AI — Shared K6 Configuration
 *
 * Central config for base URL, auth headers, SLO thresholds, and helpers.
 */

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
export const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";
export const AUTH_TOKEN_2 = __ENV.AUTH_TOKEN_2 || "";

// ---------------------------------------------------------------------------
// Headers
// ---------------------------------------------------------------------------

export function authHeaders(token) {
  const t = token || AUTH_TOKEN;
  return {
    headers: {
      Authorization: `Bearer ${t}`,
      "Content-Type": "application/json",
    },
  };
}

export function jsonHeaders() {
  return {
    headers: { "Content-Type": "application/json" },
  };
}

// ---------------------------------------------------------------------------
// SLO Thresholds (shared across all scenarios)
// ---------------------------------------------------------------------------

export const SLO_THRESHOLDS = {
  // Global error rate
  http_req_failed: ["rate<0.01"], // < 1% errors

  // Overall latency
  http_req_duration: ["p(95)<2000", "p(99)<5000"],

  // Tagged group latencies
  "http_req_duration{type:read}": ["p(95)<500"],
  "http_req_duration{type:write}": ["p(95)<1500"],
  "http_req_duration{type:ai}": ["p(95)<30000"],
  "http_req_duration{type:health}": ["p(95)<200"],
};

// ---------------------------------------------------------------------------
// Request helpers
// ---------------------------------------------------------------------------

import http from "k6/http";
import { check, group } from "k6";

/**
 * GET with auth + tagging
 */
export function authGet(path, tag, token) {
  const url = `${BASE_URL}${path}`;
  const params = {
    ...authHeaders(token),
    tags: { name: path, type: tag || "read" },
  };
  return http.get(url, params);
}

/**
 * POST with auth + JSON body + tagging
 */
export function authPost(path, body, tag, token) {
  const url = `${BASE_URL}${path}`;
  const params = {
    ...authHeaders(token),
    tags: { name: path, type: tag || "write" },
  };
  return http.post(url, JSON.stringify(body), params);
}

/**
 * PUT with auth + JSON body + tagging
 */
export function authPut(path, body, tag, token) {
  const url = `${BASE_URL}${path}`;
  const params = {
    ...authHeaders(token),
    tags: { name: path, type: tag || "write" },
  };
  return http.put(url, JSON.stringify(body), params);
}

/**
 * DELETE with auth + tagging
 */
export function authDel(path, tag, token) {
  const url = `${BASE_URL}${path}`;
  const params = {
    ...authHeaders(token),
    tags: { name: path, type: tag || "write" },
  };
  return http.del(url, null, params);
}

// ---------------------------------------------------------------------------
// Standard check helpers
// ---------------------------------------------------------------------------

export function checkStatus(res, expected, label) {
  const name = label || `status is ${expected}`;
  return check(res, { [name]: (r) => r.status === expected });
}

export function checkOk(res, label) {
  return check(res, {
    [label || "status 2xx"]: (r) => r.status >= 200 && r.status < 300,
  });
}

export function checkJson(res) {
  return check(res, {
    "response is JSON": (r) => {
      try {
        r.json();
        return true;
      } catch (_) {
        return false;
      }
    },
  });
}
