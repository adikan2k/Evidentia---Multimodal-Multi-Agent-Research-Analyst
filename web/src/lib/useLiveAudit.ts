"use client";

import { useCallback, useRef, useState } from "react";
import { streamAudit } from "@/lib/api";
import type { AuditEvent, AuditReport } from "@/lib/audit";

export type LiveAudit = {
  answer: string;
  events: AuditEvent[];
  report: AuditReport | null;
  finished: boolean;
  error: string | null;
};

/** One live audit at a time: start it from the button, read its events, stop it. */
export function useLiveAudit() {
  const [live, setLive] = useState<LiveAudit | null>(null);
  const abort = useRef<AbortController | null>(null);

  const start = useCallback((answer: string) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setLive({ answer, events: [], report: null, finished: false, error: null });
    const patch = (change: (state: LiveAudit) => LiveAudit) =>
      setLive((state) => (state && !controller.signal.aborted ? change(state) : state));
    streamAudit(
      answer,
      {
        onNode: (event) => patch((s) => ({ ...s, events: [...s.events, event] })),
        onReport: (report) => patch((s) => ({ ...s, report, finished: true })),
        onError: (message) => patch((s) => ({ ...s, finished: true, error: message })),
      },
      controller.signal,
    ).catch(() => patch((s) => ({ ...s, finished: true, error: "The connection was lost." })));
  }, []);

  /** Closing the audit also stops it on the server, so it stops costing money. */
  const stop = useCallback(() => {
    abort.current?.abort();
    setLive(null);
  }, []);

  return { live, start, stop };
}
