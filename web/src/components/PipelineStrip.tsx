"use client";

import { labelOf, MAIN_STEPS, type RunEvent, type Step, stepsOf } from "@/lib/replay";

export type StripItem = {
  key: string;
  label: string;
  /** 0 to 1. A running step in a live run has no known length, so it sits at a half. */
  progress: number;
  state: "done" | "running" | "pending";
  summary: string;
};

/** A recorded run at second `time`: every step's real start and end are known. */
export function replayItems(steps: Step[], time: number): StripItem[] {
  const running = steps.find((s) => time < s.end);
  return steps.map((step) => {
    const done = time >= step.end;
    const span = Math.max(step.end - step.start, 0.01);
    const progress = done ? 1 : step === running ? Math.max(0, (time - step.start) / span) : 0;
    const state = done ? "done" : step === running ? "running" : "pending";
    return { key: step.key, label: step.label, progress, state, summary: step.summary };
  });
}

/** A live run: the steps finished so far, then the ones still expected. */
export function liveItems(events: RunEvent[], finished: boolean): StripItem[] {
  const done: StripItem[] = stepsOf(events).map((step) => ({
    key: step.key,
    label: step.label,
    progress: 1,
    state: "done",
    summary: step.summary,
  }));
  if (finished) return done;
  const reached = events.length;
  const expected = MAIN_STEPS.slice(reached).map((node, offset): StripItem => {
    const state = offset === 0 ? "running" : "pending";
    return { key: node, label: labelOf(node), progress: offset === 0 ? 0.5 : 0, state, summary: "" };
  });
  // Past the main steps and not finished: the repair round is deciding what to do next.
  const repair: StripItem = { key: "next", label: "…", progress: 0.5, state: "running", summary: "" };
  return [...done, ...(expected.length > 0 ? expected : [repair])];
}

/** The pipeline as a row of steps that fill in as the run actually completes them. */
export function PipelineStrip({ items }: { items: StripItem[] }) {
  const running = items.find((item) => item.state === "running");
  const lastDone = [...items].reverse().find((item) => item.state === "done");
  const shown = running ?? lastDone;

  return (
    <div>
      <ol className="flex gap-1.5">
        {items.map((item, index) => (
          <li key={item.key} className="min-w-0 flex-1">
            <div className="h-[3px] overflow-hidden rounded-full bg-rule">
              <div
                className={`h-full origin-left bg-ink ${
                  item.state === "running" && item.progress === 0.5 ? "animate-pulse" : ""
                }`}
                style={{ transform: `scaleX(${item.progress})` }}
              />
            </div>
            <div
              className={`label mt-2 truncate transition-colors duration-300 ${
                item.state === "running"
                  ? "text-ink"
                  : item.state === "done"
                    ? "text-ink-soft"
                    : "text-ink-faint"
              }`}
            >
              <span className="mr-1.5 tabular-nums opacity-60">
                {String(index + 1).padStart(2, "0")}
              </span>
              {item.label}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-4 min-h-6 text-sm text-ink-soft">
        {shown && (
          <>
            <span className="font-medium text-ink">{shown.label}</span>
            <span className="mx-2 text-ink-faint">/</span>
            {shown.state === "running" ? "running" : shown.summary}
            {shown.state === "running" && <span className="ml-1 animate-pulse">…</span>}
          </>
        )}
      </p>
    </div>
  );
}
