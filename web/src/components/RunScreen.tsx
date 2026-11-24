"use client";

import { useMemo, useState } from "react";
import { ClaimList } from "@/components/ClaimList";
import { PipelineStrip } from "@/components/PipelineStrip";
import { SourcePane } from "@/components/SourcePane";
import { Transport } from "@/components/Transport";
import { endOf, type Replay, stepsOf, viewAt } from "@/lib/replay";
import { usePlayback } from "@/lib/usePlayback";

/** One run, replayed: the pipeline on top, claims on the left, the evidence on the right. */
export function RunScreen({ replay }: { replay: Replay }) {
  const duration = endOf(replay);
  const playback = usePlayback(duration);
  const steps = useMemo(() => stepsOf(replay), [replay]);
  const view = viewAt(replay, playback.time);
  const [selected, setSelected] = useState(0);

  const claim = view.claims[selected] ?? view.claims[0] ?? null;
  const recorded = new Date(replay.recorded_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div>
      <p className="label text-ink-faint">
        A real run, recorded {recorded} · {replay.models.writer} writes, {replay.models.checker}{" "}
        checks
      </p>
      <h1 className="mt-3 max-w-4xl font-serif text-5xl leading-[1.05] tracking-tight md:text-6xl">
        {replay.question}
      </h1>

      <section className="mt-10 border-y border-rule py-6">
        <PipelineStrip steps={steps} time={playback.time} />
        <div className="mt-5">
          <Transport
            time={playback.time}
            duration={duration}
            playing={playback.playing}
            speed={playback.speed}
            cost={view.cost}
            onToggle={playback.toggle}
            onRestart={playback.restart}
            onSeek={playback.seek}
            onSpeed={playback.setSpeed}
          />
        </div>
      </section>

      <section className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="label text-ink-soft">Claims</h2>
            <p className="label text-ink-faint tabular-nums">
              {view.sources.length > 0 &&
                `${view.sources.length} pages read · ${view.skipped.length} could not be used`}
            </p>
          </div>
          {view.claims.length === 0 ? (
            <Waiting queries={view.queries} sources={view.sources.map((s) => s.host)} />
          ) : (
            <ClaimList
              claims={view.claims}
              firstDraft={view.firstDraft}
              selected={selected}
              onSelect={setSelected}
            />
          )}
        </div>
        <div className="lg:sticky lg:top-8 lg:self-start">
          <h2 className="label mb-3 text-ink-soft">Source</h2>
          <SourcePane claim={claim} index={claim ? view.claims.indexOf(claim) : 0} />
        </div>
      </section>
    </div>
  );
}

/** Before any claim exists: show what the run has really produced so far. */
function Waiting({ queries, sources }: { queries: string[]; sources: string[] }) {
  if (queries.length === 0) {
    return <p className="py-6 text-sm text-ink-faint">Planning what to search for…</p>;
  }
  return (
    <div className="space-y-6 py-4">
      <div>
        <p className="label mb-2 text-ink-faint">Searching for</p>
        <ul className="space-y-1.5 font-mono text-[0.8125rem] text-ink-soft">
          {queries.map((query) => (
            <li key={query}>{query}</li>
          ))}
        </ul>
      </div>
      {sources.length > 0 && (
        <div>
          <p className="label mb-2 text-ink-faint">Reading</p>
          <p className="font-mono text-[0.8125rem] leading-relaxed text-ink-soft">
            {sources.join("  ·  ")}
          </p>
        </div>
      )}
    </div>
  );
}
