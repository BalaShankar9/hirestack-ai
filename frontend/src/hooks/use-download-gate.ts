"use client";

import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/providers";

type DownloadFn = () => void | Promise<void>;

/**
 * useDownloadGate — intercepts export/download actions.
 *
 * Flow:
 *   1. Not logged in → opens signup modal, stashes the download for later
 *   2. Logged in → executes download immediately
 */
export function useDownloadGate() {
  const { user } = useAuth();
  const [showSignup, setShowSignup] = useState(false);
  const pendingRef = useRef<DownloadFn | null>(null);

  const gatedDownload = useCallback(
    async (downloadFn: DownloadFn) => {
      // Gate: Must be authenticated
      if (!user) {
        pendingRef.current = downloadFn;
        setShowSignup(true);
        return;
      }

      // All clear — execute download
      try {
        await downloadFn();
      } catch (err) {
        console.error("Download failed:", err);
      }
    },
    [user]
  );

  // Called after successful signup — retries the stashed download
  const onSignupSuccess = useCallback(async () => {
    setShowSignup(false);
    if (pendingRef.current) {
      const fn = pendingRef.current;
      pendingRef.current = null;
      // Small delay to let auth state propagate
      await new Promise((r) => setTimeout(r, 500));
      try {
        await fn();
      } catch (err) {
        console.error("Pending download failed:", err);
      }
    }
  }, []);

  return {
    gatedDownload,
    showSignup,
    setShowSignup,
    onSignupSuccess,
  };
}
