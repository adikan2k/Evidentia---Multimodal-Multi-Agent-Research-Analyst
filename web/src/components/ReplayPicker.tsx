"use client";

import { useEffect, useState } from "react";
import { RunScreen } from "@/components/RunScreen";
import type { Replay } from "@/lib/replay";

type Entry = { id: string; question: string };

/** Loads the list of recorded runs, lets the visitor pick one, and shows it. */
export function ReplayPicker() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);

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
    <div className="mx-auto max-w-[78rem] px-6 pb-24 pt-8 md:px-10">
      <header className="mb-14 flex flex-wrap items-center justify-between gap-4">
        <p className="font-serif text-2xl italic tracking-tight">Evidentia</p>
        <nav className="label flex flex-wrap items-center gap-1 text-ink-faint">
          <span className="mr-2">Recorded runs</span>
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
      </header>
      {/* Keyed by run, so choosing another run starts it from the top with fresh state. */}
      {replay ? (
        <RunScreen key={replay.id} replay={replay} />
      ) : (
        <p className="label text-ink-faint">Loading…</p>
      )}
    </div>
  );
}
