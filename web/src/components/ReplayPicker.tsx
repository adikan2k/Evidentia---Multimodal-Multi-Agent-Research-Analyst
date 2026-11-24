"use client";

import { useEffect, useState } from "react";
import { AskBox } from "@/components/AskBox";
import { Facts } from "@/components/Facts";
import { LiveRun } from "@/components/LiveRun";
import { Mark } from "@/components/Mark";
import { RunScreen } from "@/components/RunScreen";
import { liveAvailable } from "@/lib/api";
import type { Replay } from "@/lib/replay";
import { SHELL } from "@/lib/site";
import { useLiveRun } from "@/lib/useLiveRun";

type Entry = { id: string; question: string };

/** The research tab: ask a question for a live run, or look at a recorded one. */
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

  if (live) {
    return (
      <div className={`${SHELL} pt-8`}>
        <LiveRun live={live} onClose={stop} />
      </div>
    );
  }

  return (
    <div className={SHELL}>
      <section className="grid items-end gap-x-16 gap-y-8 pt-10 pb-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pt-16 lg:pb-16">
        <div>
          <p className="label flex items-center gap-2 text-ink-soft">
            <Mark kind="tick" className="text-supported" />
            The research agent
          </p>
          <h1 className="display-1 mt-4">Every sentence shows the exact words behind it.</h1>
          <p className="lead mt-6 max-w-[38rem]">
            Ask a question. Evidentia answers from the web in short claims. Each claim carries a
            quote that code has found, word for word, on the page it cites. A second model, shown
            only the claim and the quote, decides whether one backs the other.
          </p>
        </div>
        <AskBox available={available} onAsk={start} />
      </section>

      <section aria-labelledby="recorded-runs" className="border-t border-ink pt-8">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-x-8 gap-y-3">
          <h2 id="recorded-runs" className="label text-ink">
            Recorded runs
          </h2>
          <nav aria-label="Recorded runs" className="flex flex-wrap gap-2">
            {entries.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => setChosen(entry.id)}
                aria-pressed={entry.id === chosen}
                title={entry.question}
                className={`label min-h-10 max-w-[20rem] truncate rounded-full border px-4 transition-colors ${
                  entry.id === chosen
                    ? "border-ink bg-ink text-sheet"
                    : "border-rule text-ink-soft hover:border-ink hover:text-ink"
                }`}
              >
                {entry.question}
              </button>
            ))}
          </nav>
        </div>
        {/* Keyed by run, so choosing another run starts from its own state. */}
        {replay ? (
          <RunScreen key={replay.id} replay={replay} canCheck={available === true} />
        ) : (
          <p className="label font-normal text-ink-soft">Loading the recorded run…</p>
        )}
      </section>
      <Facts />
    </div>
  );
}
