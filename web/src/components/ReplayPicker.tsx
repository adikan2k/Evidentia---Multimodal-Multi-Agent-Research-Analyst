"use client";

import { useEffect, useState } from "react";
import { AskBox } from "@/components/AskBox";
import { LiveRun } from "@/components/LiveRun";
import { Facts } from "@/components/Facts";
import { RunScreen } from "@/components/RunScreen";
import { SHELL } from "@/components/SiteHeader";
import { liveAvailable } from "@/lib/api";
import type { Replay } from "@/lib/replay";
import { useLiveRun } from "@/lib/useLiveRun";

type Entry = { id: string; question: string };

/** The home page: ask a question for a live run, or watch a recorded one. */
export function ReplayPicker() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const { live, start, stop } = useLiveRun();

  useEffect(() => {
    liveAvailable().then(setAvailable);
  }, []);

  useEffect(() => {
    fetch("/replays/index.json")
      .then((response) => response.json())
      .then((list: Entry[]) => {
        setEntries(list);
        setChosen(list[0]?.id ?? null);
      });
  }, []);

  useEffect(() => {
    if (!chosen) return;
    fetch(`/replays/${chosen}.json`)
      .then((response) => response.json())
      .then(setReplay);
  }, [chosen]);

  return (
    <div className={`${SHELL} pt-10`}>
      {live ? (
        <LiveRun live={live} onClose={stop} />
      ) : (
        <>
          <h1 className="max-w-5xl font-serif text-6xl leading-[0.98] tracking-tight md:text-8xl">
            Every sentence shows the exact words behind it.
          </h1>
          <p className="mt-7 mb-12 max-w-2xl text-lg leading-relaxed text-ink-soft">
            Evidentia answers a question from the web. Each claim carries a quote that code has
            found, word for word, on the page it cites. A second model, shown only the claim and
            the quote, decides whether one backs the other.
          </p>
          <AskBox available={available} onAsk={start} />

          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-6">
            <p className="label text-ink-soft">Or watch a recorded run</p>
            <nav className="label flex flex-wrap items-center gap-1 text-ink-faint">
              {entries.map((entry, index) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setChosen(entry.id)}
                  aria-pressed={entry.id === chosen}
                  title={entry.question}
                  className={`rounded-full border px-3 py-1.5 transition-colors ${
                    entry.id === chosen
                      ? "border-ink text-ink"
                      : "border-rule hover:border-ink-faint hover:text-ink-soft"
                  }`}
                >
                  {String(index + 1).padStart(2, "0")}
                </button>
              ))}
            </nav>
          </div>
          {/* Keyed by run, so choosing another run starts it from the top with fresh state. */}
          {replay ? (
            <RunScreen key={replay.id} replay={replay} canCheck={available === true} />
          ) : (
            <p className="label text-ink-faint">Loading…</p>
          )}
          <Facts />
        </>
      )}
    </div>
  );
}
