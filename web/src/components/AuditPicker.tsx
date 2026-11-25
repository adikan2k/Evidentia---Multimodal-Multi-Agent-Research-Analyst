"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LiveAuditScreen, RecordedAuditScreen } from "@/components/AuditScreen";
import { Mark } from "@/components/Mark";
import { SHELL } from "@/lib/site";
import { auditAvailable } from "@/lib/api";
import type { RecordedAudit } from "@/lib/audit";
import { useLiveAudit } from "@/lib/useLiveAudit";

type Entry = { id: string; question: string; model: string };

const MIN = 20;
const MAX = 12_000;

const STEPS = [
  {
    title: "It reads every cited page",
    text: "Code finds each citation in the answer and fetches the page, obeying robots.txt. The answer is split into single claims, each tied to the page it cites.",
  },
  {
    title: "Two judges check each claim",
    text: "One finds exact quotes on the page, which code verifies word for word, and rules on those quotes alone. The other reads the claim against the page as a whole.",
  },
  {
    title: "A verdict needs both to agree",
    text: "When they agree, the claim is marked. When they disagree, it is marked for a person, with both reasons shown. Nothing is settled by one model's word.",
  },
];

/** The home page: paste an answer for a live audit, or look at a recorded one. */
export function AuditPicker({ initial }: { initial?: string }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [chosen, setChosen] = useState<string | null>(initial ?? null);
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
        setChosen((c) => c ?? list.find((e) => e.id === "crispr")?.id ?? list[0]?.id ?? null);
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

  if (live) {
    return (
      <div className={SHELL}>
        <LiveAuditScreen
          events={live.events}
          report={live.report}
          finished={live.finished}
          error={live.error}
          onClose={stop}
        />
      </div>
    );
  }

  return (
    <div className={SHELL}>
      <section className="grid items-end gap-x-16 gap-y-8 pt-10 pb-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pt-16 lg:pb-16">
        <div>
          <p className="label flex items-center gap-2 text-ink-soft">
            <Mark kind="tick" className="text-supported" />
            An auditor for AI answers
          </p>
          <h1 className="display-1 mt-4">Do the citations say what the answer says?</h1>
          <p className="lead mt-6 max-w-[38rem]">
            Paste an answer from an AI tool, with its sources. Evidentia reads every cited page
            and marks each claim like an editor would: backed, partly backed, not on the page, or
            contradicted.
          </p>
          <p className="mt-5">
            <Link href="/findings" className="label text-ink underline underline-offset-4">
              Two AI search tools audited on the same questions, and a hand check of the auditor
            </Link>
          </p>
        </div>

        <form
          className="sheet p-4 md:p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) start(answer);
          }}
        >
          <label htmlFor="answer" className="label text-ink">
            The answer to audit
          </label>
          <textarea
            id="answer"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={6}
            maxLength={MAX}
            placeholder="Paste the answer here, with its links or its numbered sources…"
            className="sheet-text mt-2 w-full resize-y rounded-[3px] border border-rule bg-paper/40 p-3 text-[1.0625rem] leading-relaxed text-ink placeholder:text-ink-faint focus:border-ink focus:outline-none"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="label font-normal text-ink-soft">
              {available === false
                ? "Live audits are paused right now. The recorded ones below still open."
                : `${length.toLocaleString()} of ${MAX.toLocaleString()} characters. An audit costs this site about a cent.`}
            </p>
            <button
              type="submit"
              disabled={!ready}
              className="label min-h-11 rounded-full bg-ink px-6 text-sheet transition-opacity hover:opacity-85 disabled:opacity-35"
            >
              Audit it
            </button>
          </div>
        </form>
      </section>

      <section aria-labelledby="recorded" className="border-t border-ink pt-8">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-x-8 gap-y-3">
          <h2 id="recorded" className="label text-ink">
            Recorded audits of real answers
          </h2>
          <nav aria-label="Recorded audits" className="flex flex-wrap gap-2">
            {entries.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => setChosen(entry.id)}
                aria-pressed={entry.id === chosen}
                title={entry.question}
                className={`label min-h-10 max-w-[22rem] truncate rounded-full border px-4 transition-colors ${
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
        {/* Keyed by audit, so choosing another one starts from its own state. */}
        {audit ? (
          <>
            <RecordedAuditScreen key={audit.id} audit={audit} />
            <p className="label mt-5 font-normal text-ink-soft">
              <Link href={`/recorded/${audit.id}`} className="text-ink underline underline-offset-4">
                A link to this audit
              </Link>
              , to send to someone.
            </p>
          </>
        ) : (
          <p className="label font-normal text-ink-soft">Loading the recorded audit…</p>
        )}
      </section>

      <section aria-labelledby="how" className="mt-24 border-t border-ink pt-10">
        <h2 id="how" className="display-2 max-w-[40rem]">
          How a claim gets its mark
        </h2>
        <ol className="mt-10 grid gap-x-12 gap-y-10 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <p className="data text-ink-faint">Step {index + 1}</p>
              <h3 className="display-3 mt-2">{step.title}</h3>
              <p className="mt-3 leading-relaxed text-ink-soft">{step.text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-10 leading-relaxed text-ink-soft">
          <Link href="/method" className="text-ink underline underline-offset-4">
            The method and its limits
          </Link>
          , including what the auditor gets wrong.
        </p>
      </section>
    </div>
  );
}
