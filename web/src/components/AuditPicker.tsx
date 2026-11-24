"use client";

import { useEffect, useState } from "react";
import { LiveAuditScreen, RecordedAuditScreen } from "@/components/AuditScreen";
import { SiteHeader } from "@/components/SiteHeader";
import { auditAvailable } from "@/lib/api";
import type { RecordedAudit } from "@/lib/audit";
import { useLiveAudit } from "@/lib/useLiveAudit";

type Entry = { id: string; question: string; model: string };

const MIN = 20;
const MAX = 12_000;

/** The audit page: paste an answer for a live audit, or watch a recorded one. */
export function AuditPicker() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [audit, setAudit] = useState<RecordedAudit | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [answer, setAnswer] = useState("");
  const { live, start, stop } = useLiveAudit();

  useEffect(() => {
    auditAvailable().then(setAvailable);
  }, []);

  useEffect(() => {
    fetch("/audits/index.json")
      .then((r) => r.json())
      .then((list: Entry[]) => {
        setEntries(list);
        // The CRISPR audit has a little of everything, so it opens first when present.
        setChosen(list.find((e) => e.id === "crispr")?.id ?? list[0]?.id ?? null);
      });
  }, []);

  useEffect(() => {
    if (!chosen) return;
    fetch(`/audits/${chosen}.json`)
      .then((r) => r.json())
      .then(setAudit);
  }, [chosen]);

  const length = answer.trim().length;
  // Usable at once: while the status is still unknown, the server is probably waking up, and
  // the audit request itself will wait for it.
  const ready = available !== false && length >= MIN && length <= MAX;

  return (
    <div className="mx-auto max-w-[78rem] px-6 pb-24 pt-8 md:px-10">
      <SiteHeader />
      {live ? (
        <LiveAuditScreen
          events={live.events}
          report={live.report}
          finished={live.finished}
          error={live.error}
          onClose={stop}
        />
      ) : (
        <>
          <h1 className="max-w-5xl font-serif text-6xl leading-[0.98] tracking-tight md:text-8xl">
            Do the citations say what the answer says?
          </h1>
          <p className="mt-7 mb-10 max-w-2xl text-lg leading-relaxed text-ink-soft">
            Paste an answer from an AI tool, with its sources. Evidentia reads every cited page and
            checks each claim twice: once against exact quotes found on the page by code, once
            against the page as a whole. A claim gets a verdict only when both checks agree.
          </p>

          <form
            className="mb-12"
            onSubmit={(e) => {
              e.preventDefault();
              if (ready) start(answer);
            }}
          >
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={7}
              maxLength={MAX}
              placeholder="Paste an answer with its links or numbered sources here…"
              className="w-full resize-y rounded-lg border border-rule bg-white/70 p-4 text-[0.9375rem] leading-relaxed text-ink placeholder:text-ink-faint focus:border-ink-soft focus:outline-none"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="label text-ink-faint">
                {available === false
                  ? "Live audits are paused right now. The recorded ones below still play."
                  : `${length.toLocaleString()} / ${MAX.toLocaleString()} characters · about a cent per audit, paid by this site`}
              </p>
              <button
                type="submit"
                disabled={!ready}
                className="label rounded-full bg-ink px-5 py-2.5 text-paper transition-opacity disabled:opacity-30"
              >
                Audit it
              </button>
            </div>
          </form>

          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-6">
            <p className="label text-ink-soft">Or watch a recorded audit</p>
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
          {/* Keyed by audit, so choosing another one starts it from the top. */}
          {audit ? (
            <RecordedAuditScreen key={audit.id} audit={audit} />
          ) : (
            <p className="label text-ink-faint">Loading…</p>
          )}
        </>
      )}
    </div>
  );
}
