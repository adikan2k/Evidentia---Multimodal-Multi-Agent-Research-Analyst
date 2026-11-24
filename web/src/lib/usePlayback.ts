"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** A clock for replaying a recorded run: play, pause, change speed, jump to a moment. */
export function usePlayback(duration: number, initialSpeed = 2) {
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(initialSpeed);
  const lastFrame = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      lastFrame.current = null;
      return;
    }
    let frame = 0;
    const tick = (now: number) => {
      const elapsed = lastFrame.current === null ? 0 : (now - lastFrame.current) / 1000;
      lastFrame.current = now;
      setTime((t) => {
        const next = Math.min(t + elapsed * speed, duration);
        if (next >= duration) setPlaying(false);
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, duration]);

  const restart = useCallback(() => {
    setTime(0);
    setPlaying(true);
  }, []);

  const seek = useCallback((t: number) => setTime(Math.max(0, Math.min(t, duration))), [duration]);

  const toggle = useCallback(() => {
    // Pressing play at the end starts over.
    setTime((t) => (t >= duration ? 0 : t));
    setPlaying((p) => !p);
  }, [duration]);

  return { time, playing, speed, setSpeed, toggle, restart, seek };
}
