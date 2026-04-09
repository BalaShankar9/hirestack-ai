"use client";

import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/providers";
import { useQuota } from "@/contexts/quota-context";

type DownloadFn = () => void | Promise<void>;

/**
 * useDownloadGate — intercepts export/download actions.
 *
 * Flow:
 *   1. Not logged in → opens signup modal, stashes the download for later
 *   2. Logged in, quota OK → executes download, records usage
 *   3. Quota exceeded → opens upgrade modal
 */
export function useDownloadGate() {
  const { user } = useAuth();
  const { checkQuota, recordUsage } = useQuota();
  const [showSignup, setShowSignup] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const pendingRef = useRef<DownloadFn | null>(null);

  const gatedDownload = useCallback(
    async (downloadFn: DownloadFn) => {
      // Gate 1: Must be authenticated
      if (!user) {
        pendingRef.current = downloadFn;
        setShowSignup(true);
        return;
      }

      // TESTING MODE: quota gate disabled — re-enable for production
      // const { allowed } = checkQuota("exports");
      // if (!allowed) { setShowUpgrade(true); return; }

      // All clear — execute download
      try {
        await downloadFn();
        await recordUsage("exports");
      } catch (err) {
        console.error("Download failed:", err);
      }
    },
    [user, checkQuota, recordUsage]
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
        await recordUsage("exports");
      } catch (err) {
        console.error("Pending download failed:", err);
      }
    }
  }, [recordUsage]);

  return {
    gatedDownload,
    showSignup,
    setShowSignup,
    showUpgrade,
    setShowUpgrade,
    onSignupSuccess,
  };
}
