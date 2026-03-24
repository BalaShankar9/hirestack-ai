"use client";

import { useCallback, useState } from "react";

export interface AgentStage {
  stage: string;
  status: "waiting" | "running" | "completed" | "failed";
  latency_ms: number;
  message: string;
}

export interface AgentStatusState {
  stages: AgentStage[];
  isRunning: boolean;
  currentStage: string | null;
  qualityScores: Record<string, number>;
  factCheckSummary: { verified: number; enhanced: number; fabricated: number } | null;
  error: string | null;
}

const INITIAL_STATE: AgentStatusState = {
  stages: [],
  isRunning: false,
  currentStage: null,
  qualityScores: {},
  factCheckSummary: null,
  error: null,
};

/**
 * State container for agent pipeline progress.
 *
 * Usage: call `subscribe()` to mark the pipeline as running, then feed SSE
 * events via `handleAgentEvent`, `handleComplete`, and `handleError`.
 * The caller is responsible for managing the EventSource connection.
 */
export function useAgentStatus(): {
  state: AgentStatusState;
  subscribe: (pipelineName: string) => void;
  reset: () => void;
  handleAgentEvent: (event: { stage: string; status: string; latency_ms: number; message: string }) => void;
  handleComplete: (data: { quality_scores?: Record<string, number>; fact_check_summary?: any }) => void;
  handleError: (message: string) => void;
} {
  const [state, setState] = useState<AgentStatusState>(INITIAL_STATE);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const subscribe = useCallback((pipelineName: string) => {
    setState((prev) => ({ ...prev, isRunning: true, stages: [], error: null }));
  }, []);

  const handleAgentEvent = useCallback((event: { stage: string; status: string; latency_ms: number; message: string }) => {
    setState((prev) => {
      const existingIdx = prev.stages.findIndex((s) => s.stage === event.stage);
      const newStage: AgentStage = {
        stage: event.stage,
        status: event.status as AgentStage["status"],
        latency_ms: event.latency_ms,
        message: event.message,
      };

      const stages = [...prev.stages];
      if (existingIdx >= 0) {
        stages[existingIdx] = newStage;
      } else {
        stages.push(newStage);
      }

      return {
        ...prev,
        stages,
        currentStage: event.status === "running" ? event.stage : prev.currentStage,
      };
    });
  }, []);

  const handleComplete = useCallback((data: { quality_scores?: Record<string, number>; fact_check_summary?: any }) => {
    setState((prev) => ({
      ...prev,
      isRunning: false,
      currentStage: null,
      qualityScores: data.quality_scores || {},
      factCheckSummary: data.fact_check_summary || null,
    }));
  }, []);

  const handleError = useCallback((message: string) => {
    setState((prev) => ({ ...prev, isRunning: false, error: message }));
  }, []);

  return { state, subscribe, reset, handleAgentEvent, handleComplete, handleError };
}
