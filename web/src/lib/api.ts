// Talking to the Evidentia API: start a live run and read its events, or check one claim.

import type { AuditEvent, AuditReport } from "@/lib/audit";
import type { Label, Replay, RunEvent } from "@/lib/replay";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Verdict = { label: Label; verdict: string; reason: string };

type Handlers = {
  onNode: (event: RunEvent) => void;
  onReport: (report: Replay["report"]) => void;
  onError: (message: string) => void;
};

async function messageOf(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.message ?? "The request was refused.";
  } catch {
    return "The server could not be reached.";
  }
}

/** Whether a live run is possible right now. False if the API is down or over its budget. */
export async function liveAvailable(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/status`);
    return response.ok && (await response.json()).live_available === true;
  } catch {
    return false;
  }
}

/** Whether a live audit is possible right now. False if the API is down or over its budget. */
export async function auditAvailable(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/status`);
    return response.ok && (await response.json()).audit_available === true;
  } catch {
    return false;
  }
}

/** Start a run and call the handlers as its server-sent events arrive. */
export async function streamRun(question: string, handlers: Handlers, signal: AbortSignal) {
  return stream("/runs", { question }, handlers, signal);
}

type AuditHandlers = {
  onNode: (event: AuditEvent) => void;
  onReport: (report: AuditReport) => void;
  onError: (message: string) => void;
};

/** Start an audit of a pasted answer and call the handlers as its events arrive. */
export async function streamAudit(answer: string, handlers: AuditHandlers, signal: AbortSignal) {
  return stream("/audits", { answer }, handlers as unknown as Handlers, signal);
}

async function stream(path: string, body: object, handlers: Handlers, signal: AbortSignal) {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    handlers.onError("The server could not be reached.");
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError(await messageOf(response));
    return;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    // Events are separated by a blank line; a chunk may end in the middle of one.
    let split = buffer.indexOf("\n\n");
    while (split >= 0) {
      dispatch(buffer.slice(0, split), handlers);
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf("\n\n");
    }
  }
}

function dispatch(block: string, handlers: Handlers) {
  const name = block.match(/^event: (.*)$/m)?.[1];
  const data = block.match(/^data: (.*)$/m)?.[1];
  if (!name || !data) return;
  const payload = JSON.parse(data);
  if (name === "node") handlers.onNode(payload);
  if (name === "report") handlers.onReport(payload);
  if (name === "error") handlers.onError(payload.message);
}

/** Try to break it: ask the checker about any wording of a claim against a quote. */
export async function checkClaim(claim: string, quote: string): Promise<Verdict | string> {
  try {
    const response = await fetch(`${API_URL}/check`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ claim, quote }),
    });
    return response.ok ? await response.json() : await messageOf(response);
  } catch {
    return "The server could not be reached.";
  }
}
