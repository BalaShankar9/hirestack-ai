/**
 * S14-F3c: React hook for live token streaming.
 *
 * Subscribes to the token-stream bus and re-renders whenever new tokens
 * for the given (stage, documentKind) arrive. Components use this to paint
 * the workspace document preview live with a blinking cursor while the
 * agent generates, then swap to the formatted document on completion.
 */

import { useEffect, useState } from "react";

import {
  getTokenStreamBuffer,
  subscribeTokenStream,
} from "@/lib/streams/token-stream-bus";

export interface UseTokenStreamResult {
  /** Accumulated text streamed so far (empty string before the first chunk). */
  buffer: string;
  /** True once at least one chunk has arrived (drives cursor / placeholder UX). */
  isStreaming: boolean;
}

export function useTokenStream(
  stage: string,
  documentKind: string,
): UseTokenStreamResult {
  const [buffer, setBuffer] = useState<string>(() =>
    getTokenStreamBuffer(stage, documentKind),
  );
  const [isStreaming, setIsStreaming] = useState<boolean>(() => {
    return getTokenStreamBuffer(stage, documentKind).length > 0;
  });

  useEffect(() => {
    // Re-prime in case the keys changed.
    setBuffer(getTokenStreamBuffer(stage, documentKind));
    const unsubscribe = subscribeTokenStream(stage, documentKind, (next, payload) => {
      setBuffer(next);
      // sequence === -1 is the reset sentinel — clear the streaming flag.
      if (payload.sequence < 0 && next.length === 0) {
        setIsStreaming(false);
      } else {
        setIsStreaming(true);
      }
    });
    return unsubscribe;
  }, [stage, documentKind]);

  return { buffer, isStreaming };
}
