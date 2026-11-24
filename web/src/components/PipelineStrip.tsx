"use client";

import { Mark } from "@/components/Mark";
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

/**
 * The steps, as a list that fills in as the run really completes them. In the left rail of a
 * wide screen it is a column, each finished step with what it found. On narrower screens it
 * wraps as a row of short names, with the latest step's finding written out underneath.
 */
export function PipelineStrip({ items }: { items: StripItem[] }) {
  const running = items.find((item) => item.state === "running");
  const lastDone = [...items].reverse().find((item) => item.state === "done");
  const shown = running ?? lastDone;

  return (
    <div>
      <ol className="flex flex-wrap gap-x-5 gap-y-2 2xl:flex-col 2xl:gap-y-3.5">
        {items.map((item) => (
          <li key={item.key} className="min-w-0">
            <div
              className={`label flex items-center gap-2 transition-colors duration-300 ${
                item.state === "pending" ? "text-ink-faint" : "text-ink"
              }`}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                {item.state === "done" && <Mark kind="tick" draw className="text-supported" />}
                {item.state === "running" && (
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-ink" />
                )}
                {item.state === "pending" && (
                  <span className="h-2.5 w-2.5 rounded-full border border-ink-faint" />
                )}
              </span>
              <span className="whitespace-nowrap">{item.label}</span>
            </div>
            {item.state === "done" && item.summary && (
              <p className="label mt-0.5 hidden pl-7 font-normal text-ink-soft 2xl:block">
                {item.summary}
              </p>
            )}
          </li>
        ))}
      </ol>
      <p className="label mt-3 min-h-5 font-normal text-ink-soft 2xl:hidden">
        {shown && (
          <>
            <span className="font-medium text-ink">{shown.label}:</span>{" "}
            {shown.state === "running" ? "running…" : shown.summary}
          </>
        )}
      </p>
    </div>
  );
}
