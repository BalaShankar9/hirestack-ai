/**
 * Runtime environment variable validation.
 *
 * Called once at app startup from the root Providers component.
 * Fails loudly in development (console.error) and silently in production
 * so the app degrades gracefully instead of crashing.
 *
 * IMPORTANT: Next.js only performs static replacement of LITERAL
 * `process.env.NEXT_PUBLIC_*` references. Dynamic access like
 * `process.env[name]` does NOT work — the value will always be
 * undefined at runtime. Therefore we build a lookup map from
 * literal references below.
 */

/**
 * Build-time resolved env values.
 * Each key MUST use a literal `process.env.NEXT_PUBLIC_*` expression
 * so that Next.js replaces it at build time.
 */
const ENV_VALUES: Record<string, string | undefined> = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
};

interface EnvSpec {
  name: string;
  required: boolean;
  /** Optional predicate; returns an error string on failure. */
  validate?: (value: string) => string | null;
}

const ENV_SPECS: EnvSpec[] = [
  {
    name: "NEXT_PUBLIC_SUPABASE_URL",
    required: true,
    validate: (v) =>
      v.startsWith("https://") ? null : "NEXT_PUBLIC_SUPABASE_URL must start with https://",
  },
  {
    name: "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    required: true,
    validate: (v) =>
      v.length > 20 ? null : "NEXT_PUBLIC_SUPABASE_ANON_KEY looks too short — is it correct?",
  },
  {
    name: "NEXT_PUBLIC_API_URL",
    required: false,
    validate: (v) =>
      !v || v.startsWith("http://") || v.startsWith("https://")
        ? null
        : "NEXT_PUBLIC_API_URL must start with http:// or https://",
  },
];

export interface EnvValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export function validateEnv(): EnvValidationResult {
  // Only run on the client (Next.js runs this file both server and client side)
  if (typeof window === "undefined") return { valid: true, errors: [], warnings: [] };

  const errors: string[] = [];
  const warnings: string[] = [];

  for (const spec of ENV_SPECS) {
    const value = ENV_VALUES[spec.name] ?? "";

    if (!value) {
      if (spec.required) {
        errors.push(`Missing required env var: ${spec.name}`);
      } else {
        warnings.push(`Optional env var not set: ${spec.name}`);
      }
      continue;
    }

    if (spec.validate) {
      const msg = spec.validate(value);
      if (msg) {
        if (spec.required) {
          errors.push(msg);
        } else {
          warnings.push(msg);
        }
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * Run env validation and report to the console.
 * Safe to call multiple times — results are memoised.
 */
let _ran = false;
export function checkEnvOnce(): void {
  if (_ran || typeof window === "undefined") return;
  _ran = true;

  const result = validateEnv();

  if (result.errors.length > 0) {
    console.error(
      "[HireStack] ⚠️  Environment misconfiguration detected:\n" +
        result.errors.map((e) => `  • ${e}`).join("\n") +
        "\n  Copy frontend/.env.example to frontend/.env.local and fill in the values.",
    );
  }

  if (result.warnings.length > 0 && process.env.NODE_ENV !== "production") {
    console.warn(
      "[HireStack] Environment warnings:\n" + result.warnings.map((w) => `  • ${w}`).join("\n"),
    );
  }
}
