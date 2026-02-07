"use client";

import { useCallback, useEffect, useState } from "react";

export type ToastVariant = "default" | "success" | "error" | "warning";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

type ToastAction =
  | { type: "ADD"; toast: Toast }
  | { type: "REMOVE"; id: string }
  | { type: "CLEAR" };

const listeners: Set<(action: ToastAction) => void> = new Set();
let toasts: Toast[] = [];

function dispatch(action: ToastAction) {
  switch (action.type) {
    case "ADD":
      toasts = [...toasts, action.toast];
      break;
    case "REMOVE":
      toasts = toasts.filter((t) => t.id !== action.id);
      break;
    case "CLEAR":
      toasts = [];
      break;
  }
  listeners.forEach((listener) => listener(action));
}

let counter = 0;

/** Imperative toast function — works anywhere, no hook needed */
export function toast({
  title,
  description,
  variant = "default",
  duration = 4000,
}: Omit<Toast, "id">) {
  const id = `toast-${++counter}`;
  dispatch({ type: "ADD", toast: { id, title, description, variant, duration } });

  if (duration > 0) {
    setTimeout(() => dispatch({ type: "REMOVE", id }), duration);
  }

  return id;
}

toast.success = (title: string, description?: string) =>
  toast({ title, description, variant: "success" });

toast.error = (title: string, description?: string) =>
  toast({ title, description, variant: "error", duration: 6000 });

toast.warning = (title: string, description?: string) =>
  toast({ title, description, variant: "warning" });

/** React hook for components that render toasts */
export function useToast() {
  const [state, setState] = useState<Toast[]>([...toasts]);

  useEffect(() => {
    const listener = () => setState([...toasts]);
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, []);

  const dismiss = useCallback((id: string) => {
    dispatch({ type: "REMOVE", id });
  }, []);

  return { toasts: state, dismiss, toast };
}
