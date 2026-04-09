/**
 * Shared pricing plan definitions.
 * Used by: pricing page, billing settings, upgrade modal, quota context.
 */

export interface PlanTier {
  key: string;
  name: string;
  price: number;
  popular?: boolean;
  features: string[];
  limits: {
    applications: number;  // -1 = unlimited
    exports: number;
    ats_scans: number;
    ai_calls: number;
    members: number;
    candidates: number;
  };
}

export const PLANS: PlanTier[] = [
  {
    key: "free",
    name: "Free",
    price: 0,
    limits: { applications: 5, exports: 5, ats_scans: 10, ai_calls: 50, members: 1, candidates: 0 },
    features: [
      "5 applications per month",
      "5 document exports",
      "10 ATS scans",
      "Standard document types",
      "Basic company intel",
    ],
  },
  {
    key: "starter",
    name: "Starter",
    price: 19,
    limits: { applications: 15, exports: -1, ats_scans: 30, ai_calls: 200, members: 1, candidates: 0 },
    features: [
      "15 applications per month",
      "Unlimited exports",
      "30 ATS scans",
      "All 35+ document types",
      "Full company intel",
      "LinkedIn analysis",
      "Email support",
    ],
  },
  {
    key: "pro",
    name: "Pro",
    price: 49,
    popular: true,
    limits: { applications: 50, exports: -1, ats_scans: 200, ai_calls: 1000, members: 5, candidates: 0 },
    features: [
      "50 applications per month",
      "Unlimited exports",
      "200 ATS scans",
      "All document types",
      "Deep company research",
      "Market intelligence",
      "Interview prep (unlimited)",
      "Salary coach (unlimited)",
      "5 team members",
      "Priority support",
    ],
  },
  {
    key: "agency",
    name: "Agency",
    price: 149,
    limits: { applications: -1, exports: -1, ats_scans: -1, ai_calls: -1, members: 20, candidates: -1 },
    features: [
      "Unlimited applications",
      "Unlimited everything",
      "20 team members",
      "Unlimited candidates",
      "Candidate pipeline",
      "Full API access",
      "White-label branding",
      "Dedicated support",
    ],
  },
];

export function getPlan(key: string): PlanTier {
  return PLANS.find((p) => p.key === key) || PLANS[0];
}

export function isUnlimited(limit: number): boolean {
  return limit === -1;
}

export function isWithinLimit(usage: number, limit: number): boolean {
  // TESTING MODE: all limits bypassed — re-enable for production
  return true;
}
