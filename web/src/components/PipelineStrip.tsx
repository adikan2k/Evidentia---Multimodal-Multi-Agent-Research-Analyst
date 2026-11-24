"use client";

import type { Step } from "@/lib/replay";

/** The pipeline as a row of steps. A step fills in as the recorded run actually ran it. */
export function PipelineStrip({ steps, time }: { steps: Step[]; time: number }) {
  const current = steps.find((s) => time < s.end) ?? null;
  const shown = current ?? steps[steps.length - 1];

  return (
    <div>
      <ol className="flex gap-1.5">
        {steps.map((step, index) => {
          const done = time >= step.end;
          const running = step === current;
          const progress = running
            ? Math.min(1, Math.max(0, (time - step.start) / Math.max(step.end - step.start, 0.01)))
            : done
              ? 1
              : 0;
          return (
            <li key={step.key} className="min-w-0 flex-1">
              <div className="h-[3px] overflow-hidden rounded-full bg-rule">
                <div
                  className="h-full origin-left bg-ink"
                  style={{ transform: `scaleX(${progress})` }}
                />
              </div>
              <div
                className={`label mt-2 truncate transition-colors duration-300 ${
                  running ? "text-ink" : done ? "text-ink-soft" : "text-ink-faint"
                }`}
              >
                <span className="mr-1.5 tabular-nums opacity-60">
                  {String(index + 1).padStart(2, "0")}
                </span>
                {step.label}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 min-h-6 text-sm text-ink-soft">
        {shown && (
          <>
            <span className="font-medium text-ink">{shown.label}</span>
            <span className="mx-2 text-ink-faint">/</span>
            {current ? "running" : shown.summary}
            {current && <span className="ml-1 animate-pulse">…</span>}
          </>
        )}
      </p>
    </div>
  );
}
