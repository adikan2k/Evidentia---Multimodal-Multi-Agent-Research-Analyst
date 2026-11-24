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

/** Play, pause, scrub and speed for a recorded run, with the run's clock and cost so far. */
export function Transport(props: Props) {
  const { time, duration, playing, speed, cost } = props;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <button
        type="button"
        onClick={props.onToggle}
        className="label rounded-full bg-ink px-4 py-2 text-paper transition-opacity hover:opacity-85"
      >
        {playing ? "Pause" : time >= duration ? "Play again" : "Play"}
      </button>
      <button
        type="button"
        onClick={props.onRestart}
        className="label text-ink-soft underline-offset-4 hover:text-ink hover:underline"
      >
        Restart
      </button>
      <input
        type="range"
        min={0}
        max={duration}
        step={0.05}
        value={time}
        onChange={(e) => props.onSeek(Number(e.target.value))}
        aria-label="Position in the recorded run"
        className="h-1 min-w-40 flex-1 cursor-pointer appearance-none rounded-full bg-rule accent-ink"
      />
      <div className="label flex items-center gap-1 text-ink-faint">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => props.onSpeed(s)}
            aria-pressed={speed === s}
            className={`rounded px-1.5 py-1 transition-colors ${
              speed === s ? "bg-paper-deep text-ink" : "hover:text-ink"
            }`}
          >
            {s}×
          </button>
        ))}
      </div>
      <div className="label flex gap-4 text-ink-soft tabular-nums">
        <span>{time.toFixed(1)}s</span>
        <span>${cost.toFixed(3)}</span>
      </div>
    </div>
  );
}
