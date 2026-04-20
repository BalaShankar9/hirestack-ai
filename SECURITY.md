# Security Policy

## Supported Versions

The `main` branch is the only actively maintained version of HireStack AI.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < main  | :x:                |

## Reporting a Vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

If you discover a security issue, report it privately by emailing the
maintainer through the address on the GitHub profile of the repository
owner, or by opening a private GitHub Security Advisory:

  https://github.com/BalaShankar9/hirestack-ai/security/advisories/new

We aim to:

- Acknowledge receipt within **3 business days**.
- Provide an initial assessment within **7 business days**.
- Ship a fix or mitigation as quickly as the severity warrants
  (critical: < 7 days; high: < 30 days; medium/low: best effort).

When reporting, please include:

1. A clear description of the vulnerability.
2. Steps to reproduce (proof-of-concept, sample request, etc.).
3. The affected component (frontend, backend, AI engine, infra).
4. Your assessment of impact (data exposure, RCE, auth bypass, etc.).

## Scope

In scope:

- The HireStack AI web application (this repository)
- The FastAPI backend
- The Next.js frontend
- The AI orchestration engine (`ai_engine/`)
- Supabase RLS policies shipped in `supabase/migrations/`
- Stripe webhook handling

Out of scope:

- Third-party services (Supabase, Stripe, Gemini) — report to those
  vendors directly.
- Self-hosted deployments where the operator has modified security
  configuration (CSP, RLS, auth) from the shipped defaults.
- Denial-of-service via volumetric traffic (handled by infra rate
  limits, not application code).

## Coordinated Disclosure

We follow coordinated disclosure: we will work with you on a fix
timeline, credit your finding in the release notes (unless you prefer
to remain anonymous), and request that the issue stay private until a
patch is available.

Thank you for helping keep HireStack AI users safe.
