/**
 * Lightweight client-side error reporting.
 *
 * Captures uncaught errors and React error-boundary crashes, then
 * POSTs them to the backend `/api/frontend-errors` collector endpoint
 * (which can forward to Sentry, Loki, etc.).
 *
 * No heavy SDK required on the client.
 */

const REPORT_URL = "/api/backend/frontend-errors";
const MAX_QUEUE = 20;
const FLUSH_MS = 5_000;

interface ErrorReport {
  message: string;
  stack?: string;
  componentStack?: string;
  url: string;
  timestamp: string;
  userAgent: string;
}

let queue: ErrorReport[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function enqueue(report: ErrorReport) {
  if (queue.length >= MAX_QUEUE) return;          // back-pressure
  queue.push(report);
  if (!timer) {
    timer = setTimeout(flush, FLUSH_MS);
  }
}

async function flush() {
  timer = null;
  if (queue.length === 0) return;
  const batch = queue.splice(0, MAX_QUEUE);
  try {
    await fetch(REPORT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ errors: batch }),
      keepalive: true,                             // survive page unload
    });
  } catch {
    // Swallow — error reporting must never crash the app
  }
}

/**
 * Report an error from an ErrorBoundary's componentDidCatch.
 */
export function reportError(error: Error, componentStack?: string) {
  enqueue({
    message: error.message,
    stack: error.stack?.slice(0, 2000),
    componentStack: componentStack?.slice(0, 1000),
    url: typeof window !== "undefined" ? window.location.href : "",
    timestamp: new Date().toISOString(),
    userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "",
  });
}

/**
 * Install global listeners for uncaught errors and unhandled rejections.
 * Call once in the root layout or providers.
 */
export function installGlobalErrorHandler() {
  if (typeof window === "undefined") return;

  window.addEventListener("error", (event) => {
    reportError(
      event.error instanceof Error
        ? event.error
        : new Error(event.message || "Unknown error"),
    );
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportError(
      reason instanceof Error
        ? reason
        : new Error(String(reason ?? "Unhandled promise rejection")),
    );
  });

  // Flush on page hide (tab close / navigation)
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
}
