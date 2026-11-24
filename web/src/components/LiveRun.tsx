"use client";

import { liveItems, PipelineStrip } from "@/components/PipelineStrip";
import { RunBody } from "@/components/RunBody";
import { viewAt } from "@/lib/replay";
import type { LiveState } from "@/lib/useLiveRun";

/** A run happening now. Nothing is simulated: the page draws events as the server sends them. */
export function LiveRun({ live, onClose }: { live: LiveState; onClose: () => void }) {
  const view = viewAt(live.events, Number.POSITIVE_INFINITY);
  view.finished = live.finished;

  return (
    <div>
      <p className="label text-ink-faint tabular-nums">
        {live.finished ? "A live run, just now" : "Running live"} · {live.seconds.toFixed(1)}s · $
        {view.cost.toFixed(3)}
      </p>
      <h2 className="mt-3 max-w-4xl font-serif text-4xl leading-[1.08] tracking-tight md:text-5xl">
        {live.question}
      </h2>
      <section className="mt-10 border-y border-rule py-6">
        <PipelineStrip items={liveItems(live.events, live.finished)} />
        <div className="mt-5 flex flex-wrap items-center gap-5">
          <button
            type="button"
            onClick={onClose}
            className="label rounded-full border border-ink px-4 py-2 transition-colors hover:bg-ink hover:text-paper"
          >
            {live.finished ? "Back to recorded runs" : "Stop and go back"}
          </button>
          {live.error && <p className="text-sm text-unverified">{live.error}</p>}
          {!live.finished && live.events.length === 0 && (
            <p className="text-sm text-ink-soft">
              <span className="animate-pulse">Starting…</span> If nobody has used the site for a
              while, the server takes about 15 seconds to wake up.
            </p>
          )}
        </div>
      </section>
      <RunBody view={view} canCheck={live.finished && !live.error} />
    </div>
  );
}
