"use client";

import { useState } from "react";
import { AuditSheet } from "@/components/AuditSheet";
import { auditViewAt, type RecordedAudit, sentencesOf } from "@/lib/audit";
import { usePlayback } from "@/lib/usePlayback";

// Played faster than it happened, and the page says so: the recording's own timings, sped up.
const SPEED = 3;

type Props = {
  audit: RecordedAudit | null;
  /** The paste form, shown on the sheet's second tab. */
  paste: React.ReactNode;
  /** Where the full audit, with its evidence, sits further down the page. */
  fullAuditId: string;
};

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The home page's first screen (D-053): a recorded audit of a real answer, replayed on its own
 * timings. Sentences are underlined as the splitter finds them; every mark is drawn when the two
 * judges' verdicts are combined, as they were in the recording. A tab switches to pasting.
 */
export function HeroSheet({ audit, paste, fullAuditId }: Props) {
  const [tab, setTab] = useState<"recorded" | "paste">("recorded");

  return (
    <div>
      <div role="tablist" aria-label="The sheet" className="flex gap-1">
        {(
          [
            ["recorded", "A real answer, audited"],
            ["paste", "Paste your own"],
          ] as const
        ).map(([key, text]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`label min-h-10 rounded-t-[4px] border border-b-0 px-4 transition-colors ${
              tab === key ? "border-rule bg-sheet text-ink" : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {text}
          </button>
        ))}
      </div>
      {tab === "recorded" ? (
        audit ? (
          <Replayed key={audit.id} audit={audit} fullAuditId={fullAuditId} />
        ) : (
          <div className="sheet min-h-[22rem] p-6">
            <p className="label font-normal text-ink-soft">Loading a recorded audit…</p>
          </div>
        )
      ) : (
        <div role="tabpanel">{paste}</div>
      )}
    </div>
  );
}

function Replayed({ audit, fullAuditId }: { audit: RecordedAudit; fullAuditId: string }) {
  const last = audit.events[audit.events.length - 1];
  const duration = (last?.t ?? 0) + 0.5;
  // Opens finished for visitors who ask for less motion.
  const [still] = useState(prefersReducedMotion);
  const playback = usePlayback(duration, SPEED, still);
  const view = auditViewAt(audit.events, playback.time);
  const claims = view.finished ? audit.report.claims : view.claims;
  const sentences = sentencesOf(claims);
  const done = view.finished;
  const flagged = claims.filter((c) => c.label === "not_found" || c.label === "contradicted").length;

  const status = !claims.length
    ? "Finding the citations and splitting the answer into claims…"
    : !view.judged
      ? `${claims.length} claims found. Two judges are reading the cited pages…`
      : `${claims.length} claims marked${flagged ? `, ${flagged} of them flagged` : ""}.`;

  return (
    <div role="tabpanel">
      <div className="[&_.sheet]:rounded-tl-none">
        <AuditSheet
          text={view.answerText || audit.answer.text}
          sentences={sentences}
          judged={view.judged || done}
          selected={null}
          onSelect={() => document.getElementById(fullAuditId)?.scrollIntoView({ behavior: "smooth" })}
          caption={`${audit.answer.model} with ${audit.answer.tool}: “${audit.question}”`}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="label font-normal text-ink-soft" aria-live="polite">
          {status}{" "}
          <span className="text-ink-faint">
            {done ? "A recording, on its real timings" : `Replayed at ${SPEED}× its real timings`}.
          </span>
        </p>
        <div className="flex items-center gap-2">
          {done && (
            <button
              type="button"
              onClick={playback.restart}
              className="label min-h-10 rounded-full border border-rule px-4 text-ink-soft transition-colors hover:border-ink hover:text-ink"
            >
              Replay
            </button>
          )}
          <a
            href={`#${fullAuditId}`}
            className="label flex min-h-10 items-center rounded-full bg-ink px-4 text-sheet transition-opacity hover:opacity-85"
          >
            See the evidence ↓
          </a>
        </div>
      </div>
    </div>
  );
}
