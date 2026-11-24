"use client";

import { useMemo } from "react";
import { PipelineStrip, replayItems } from "@/components/PipelineStrip";
import { RunBody } from "@/components/RunBody";
import { Transport } from "@/components/Transport";
import { endOf, type Replay, stepsOf, viewAt } from "@/lib/replay";
import { usePlayback } from "@/lib/usePlayback";

/** A recorded run, replayed on the timings it really had. */
export function RunScreen({ replay, canCheck }: { replay: Replay; canCheck: boolean }) {
  const duration = endOf(replay.events);
  const playback = usePlayback(duration);
  const steps = useMemo(() => stepsOf(replay.events), [replay]);
  const view = viewAt(replay.events, playback.time);
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
        <PipelineStrip items={replayItems(steps, playback.time)} />
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
      <RunBody view={view} canCheck={canCheck} />
    </div>
  );
}
