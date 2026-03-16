"use client";

import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface RetryButtonProps {
  onClick: () => void;
  className?: string;
  maxRetries?: number;
}

export function RetryButton({ onClick, className = "", maxRetries = 3 }: RetryButtonProps) {
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  const handleRetry = useCallback(() => {
    if (retryCount >= maxRetries || isRetrying) return;
    setIsRetrying(true);
    setRetryCount((c) => c + 1);
    const delay = Math.pow(2, retryCount) * 1000;
    setTimeout(() => {
      onClick();
      setIsRetrying(false);
    }, delay);
  }, [retryCount, maxRetries, onClick, isRetrying]);

  const attemptsLeft = maxRetries - retryCount;

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleRetry}
      disabled={isRetrying || attemptsLeft <= 0}
      className={className}
    >
      <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isRetrying ? "animate-spin" : ""}`} />
      {isRetrying ? "Retrying..." : attemptsLeft > 0 ? "Try again" : "Max retries reached"}
    </Button>
  );
}
