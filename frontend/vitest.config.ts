import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", ".netlify/**"],
    css: true,
    // Provide placeholder env vars so modules that guard on NEXT_PUBLIC_SUPABASE_*
    // at initialisation time (e.g. src/lib/supabase.ts) don't throw during tests.
    env: {
      NEXT_PUBLIC_SUPABASE_URL: "https://placeholder.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "placeholder-anon-key-for-tests",
      NEXT_PUBLIC_API_URL: "http://localhost:8000",
    },
  },
});
