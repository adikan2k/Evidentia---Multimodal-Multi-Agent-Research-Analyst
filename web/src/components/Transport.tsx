"use client";

type Props = {
  time: number;
  duration: number;
  playing: boolean;
  speed: number;
  cost: number;
  onToggle: () => void;
  onRestart: () => void;
  onSeek: (t: number) => void;
  onSpeed: (speed: number) => void;
};

const SPEEDS = [1, 2, 4];

/** Replay, pause, scrub and speed for a recording, with its clock and cost so far. */
export function Transport(props: Props) {
  const { time, duration, playing, speed, cost } = props;
  const atEnd = time >= duration;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <button
        type="button"
        onClick={atEnd ? props.onRestart : props.onToggle}
        className="label min-h-10 rounded-full bg-ink px-4 text-sheet transition-opacity hover:opacity-85"
      >
        {playing ? "Pause" : atEnd ? "Replay" : "Play"}
      </button>
      <input
        type="range"
        min={0}
        max={duration}
        step={0.05}
        value={time}
        onChange={(e) => props.onSeek(Number(e.target.value))}
        aria-label="Position in the recording"
        className="h-1 min-w-32 flex-1 cursor-pointer appearance-none rounded-full bg-rule accent-ink"
      />
      <div className="label flex items-center" role="group" aria-label="Replay speed">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => props.onSpeed(s)}
            aria-pressed={speed === s}
            className={`min-h-10 min-w-9 rounded px-1.5 transition-colors ${
              speed === s ? "bg-paper-deep text-ink" : "text-ink-soft hover:text-ink"
            }`}
          >
            {s}×
          </button>
        ))}
      </div>
      <div className="data flex gap-3 text-ink-soft">
        <span>{Math.min(time, duration).toFixed(1)}s</span>
        <span>${cost.toFixed(3)}</span>
      </div>
    </div>
  );
}
