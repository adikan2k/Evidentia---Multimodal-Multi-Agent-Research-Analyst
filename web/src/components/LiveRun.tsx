"use client";

import { liveItems } from "@/components/PipelineStrip";
import { RunBody } from "@/components/RunBody";
import { viewAt } from "@/lib/replay";
import type { LiveState } from "@/lib/useLiveRun";

/** A run happening now. Nothing is simulated: the page draws events as the server sends them. */
export function LiveRun({ live, onClose }: { live: LiveState; onClose: () => void }) {
  const view = viewAt(live.events, Number.POSITIVE_INFINITY);
  view.finished = live.finished;

  return (
    <div>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="data text-ink-soft">
            {live.finished ? "A live run, just now" : "Running live"} · {live.seconds.toFixed(1)}s · $
            {view.cost.toFixed(3)}
          </p>
          <h1 className="display-2 mt-2 max-w-[52rem]">{live.question}</h1>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="label min-h-10 rounded-full border border-ink px-4 transition-colors hover:bg-ink hover:text-sheet"
        >
          {live.finished ? "Back to the recorded runs" : "Stop and go back"}
        </button>
      </div>
      {live.error && <p className="label mb-6 font-normal text-unverified">{live.error}</p>}
      {!live.finished && live.events.length === 0 && (
        <p className="label mb-6 font-normal text-ink-soft">
          <span className="animate-pulse">Starting…</span> If nobody has used the site for a while,
          the server takes about 15 seconds to wake up.
        </p>
      )}
      <RunBody
        view={view}
        canCheck={live.finished && !live.error}
        strip={liveItems(live.events, live.finished)}
      />
    </div>
  );
}
