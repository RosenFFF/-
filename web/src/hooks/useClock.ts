import { useSyncExternalStore } from "react";

/** Subscribe to a low-frequency clock for countdowns (no setState-in-effect). */
export function useClock(active: boolean, intervalMs = 1000): number {
  return useSyncExternalStore(
    (onStoreChange) => {
      if (!active) return () => undefined;
      const id = window.setInterval(onStoreChange, intervalMs);
      return () => window.clearInterval(id);
    },
    () => Date.now(),
    () => 0,
  );
}

export function remainingSeconds(deadlineMs: number | null, now: number): number {
  if (deadlineMs === null) return 0;
  return Math.max(0, Math.ceil((deadlineMs - now) / 1000));
}
