"use client";

import { useMemo } from "react";
import { replayItems } from "@/components/PipelineStrip";
import { RunBody } from "@/components/RunBody";
import { Transport } from "@/components/Transport";
import { endOf, type Replay, stepsOf, viewAt } from "@/lib/replay";
import { usePlayback } from "@/lib/usePlayback";

/** A recorded run. It opens on the finished result; "Replay" plays it on its real timings. */
export function RunScreen({ replay, canCheck }: { replay: Replay; canCheck: boolean }) {
  const duration = endOf(replay.events);
  const playback = usePlayback(duration, 2, true);
  const steps = useMemo(() => stepsOf(replay.events), [replay]);
  const view = viewAt(replay.events, playback.time);
  const recorded = new Date(replay.recorded_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div>
      <p className="label font-normal text-ink-soft">
        A real run, recorded on {recorded}. {replay.models.writer} writes, {replay.models.checker} checks.
      </p>
      <h2 className="display-2 mt-2 mb-8 max-w-[52rem]">{replay.question}</h2>
      <RunBody
        view={view}
        canCheck={canCheck}
        strip={replayItems(steps, playback.time)}
        controls={
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
        }
      />
    </div>
  );
}
