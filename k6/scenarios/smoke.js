/**
 * HireStack AI — Smoke Test
 *
 * Minimal sanity check: 1-3 VUs for 1 minute.
 * Verifies all major endpoints respond without errors.
 *
 * Usage: k6 run k6/scenarios/smoke.js
 */

import { sleep } from "k6";
import { SLO_THRESHOLDS } from "../config.js";
import {
  flowHealthCheck,
  flowAuthAndProfile,
  flowDashboard,
  flowJobCrud,
  flowDocumentLibrary,
  flowCareerAnalytics,
  flowLearning,
  flowCandidates,
  flowSalary,
  flowBilling,
  flowGapReports,
} from "../flows.js";

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: 2,
      duration: "1m",
    },
  },
  thresholds: {
    ...SLO_THRESHOLDS,
    http_req_failed: ["rate<0.05"], // Relaxed to 5% for smoke
  },
};

export default function () {
  flowHealthCheck();
  flowAuthAndProfile();
  flowDashboard();
  flowJobCrud();
  flowDocumentLibrary();
  flowCareerAnalytics();
  flowLearning();
  flowCandidates();
  flowSalary();
  flowBilling();
  flowGapReports();

  sleep(1);
}
