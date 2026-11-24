"use client";

import { useCallback, useRef, useState } from "react";
import { streamRun } from "@/lib/api";
import type { RunEvent } from "@/lib/replay";

export type LiveState = {
  question: string;
  events: RunEvent[];
  finished: boolean;
  error: string | null;
  seconds: number;
};

/** One live run at a time: start it from a button press, read its events, stop it. */
export function useLiveRun() {
  const [live, setLive] = useState<LiveState | null>(null);
  const abort = useRef<AbortController | null>(null);
  const clock = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopClock = () => {
    if (clock.current) clearInterval(clock.current);
    clock.current = null;
  };

  const start = useCallback((question: string) => {
    abort.current?.abort();
    stopClock();
    const controller = new AbortController();
    abort.current = controller;
    const begun = performance.now();
    setLive({ question, events: [], finished: false, error: null, seconds: 0 });
    const patch = (change: (state: LiveState) => LiveState) =>
      setLive((state) => (state && !controller.signal.aborted ? change(state) : state));
    clock.current = setInterval(
      () => patch((s) => ({ ...s, seconds: (performance.now() - begun) / 1000 })),
      100,
    );
    streamRun(
      question,
      {
        onNode: (event) => patch((s) => ({ ...s, events: [...s.events, event] })),
        onReport: () => patch((s) => ({ ...s, finished: true })),
        onError: (message) => patch((s) => ({ ...s, finished: true, error: message })),
      },
      controller.signal,
    )
      .catch(() => patch((s) => ({ ...s, finished: true, error: "The connection was lost." })))
      .finally(stopClock);
  }, []);

  /** Closing the run also stops it on the server, so it stops costing money. */
  const stop = useCallback(() => {
    abort.current?.abort();
    stopClock();
    setLive(null);
  }, []);

  return { live, start, stop };
}
