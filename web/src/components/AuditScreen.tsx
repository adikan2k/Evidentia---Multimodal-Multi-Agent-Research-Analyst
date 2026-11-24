"use client";

import { useMemo, useState } from "react";
import { AuditEvidence } from "@/components/AuditEvidence";
import { AuditAccuracy } from "@/components/AuditScorecard";
import { AuditSheet } from "@/components/AuditSheet";
import { AuditTally } from "@/components/AuditTally";
import { PipelineStrip, replayItems, type StripItem } from "@/components/PipelineStrip";
import { Transport } from "@/components/Transport";
import {
  type AuditEvent,
  type AuditReport,
  auditSteps,
  auditViewAt,
  liveAuditItems,
  type RecordedAudit,
  sentencesOf,
} from "@/lib/audit";
import { usePlayback } from "@/lib/usePlayback";

type Desk = {
  events: AuditEvent[];
  time: number;
  report: AuditReport | null;
  strip: StripItem[];
  caption: string;
  controls?: React.ReactNode;
};

/**
 * The desk: the steps in a rail, the sheet with its marks and tally in the middle, and the
 * evidence and the auditor's own error rates on the right. Three zones side by side on a wide
 * screen, two on a laptop, one on a phone.
 */
function AuditDesk({ events, time, report, strip, caption, controls }: Desk) {
  const view = auditViewAt(events, time);
  const done = report !== null && view.finished;
  const claims = done ? report.claims : view.claims;
  const judged = view.judged || done;
  const sentences = sentencesOf(claims);
  const [selected, setSelected] = useState<number | null>(null);
  const firstNumber =
    selected === null ? 1 : sentences.slice(0, selected).reduce((n, s) => n + s.claims.length, 1);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)] 2xl:grid-cols-[14rem_minmax(0,1fr)_minmax(22rem,29rem)]">
      <aside className="lg:col-span-2 2xl:col-span-1" aria-label="Steps of the audit">
        <div className="2xl:sticky 2xl:top-6">
          <h3 className="data mb-3 text-ink-faint">Steps</h3>
          <PipelineStrip items={strip} />
          {controls && <div className="mt-4 border-t border-rule pt-4">{controls}</div>}
        </div>
      </aside>

      <div className="min-w-0">
        <AuditSheet
          text={view.answerText}
          sentences={sentences}
          judged={judged}
          selected={selected}
          onSelect={setSelected}
          caption={caption}
        >
          <AuditTally claims={claims} judged={judged} card={done ? report.scorecard : null} />
        </AuditSheet>
        {view.notRead.length > 0 && (
          <p className="label mt-4 font-normal text-ink-soft">
            Pages that could not be read: {view.notRead.map((p) => `${p.host} (${p.reason})`).join("; ")}.
          </p>
        )}
      </div>

      <aside className="space-y-6 lg:sticky lg:top-6 lg:self-start" aria-label="Evidence">
        <AuditEvidence
          sentence={selected === null ? null : (sentences[selected] ?? null)}
          firstNumber={firstNumber}
          judged={judged}
          onClose={() => setSelected(null)}
        />
        <AuditAccuracy />
      </aside>
    </div>
  );
}

/** A recorded audit. It opens on the finished result; "Replay" plays it on its real timings. */
export function RecordedAuditScreen({ audit }: { audit: RecordedAudit }) {
  const last = audit.events[audit.events.length - 1];
  const duration = (last?.t ?? 0) + 0.5;
  const playback = usePlayback(duration, 2, true);
  const steps = useMemo(() => auditSteps(audit.events), [audit]);
  const view = auditViewAt(audit.events, playback.time);
  const made = new Date(audit.answer.made_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div>
      <p className="label font-normal text-ink-soft">
        The question put to {audit.answer.model} with {audit.answer.tool}, on {made}
      </p>
      <h2 className="display-2 mt-2 mb-8 max-w-[52rem]">{audit.question}</h2>
      <AuditDesk
        events={audit.events}
        time={playback.time}
        report={audit.report}
        strip={replayItems(steps, playback.time)}
        caption={`The answer from ${audit.answer.model}, as audited`}
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

type LiveProps = {
  events: AuditEvent[];
  report: AuditReport | null;
  finished: boolean;
  error: string | null;
  onClose: () => void;
};

/** A live audit, drawn from its events as they arrive. */
export function LiveAuditScreen({ events, report, finished, error, onClose }: LiveProps) {
  return (
    <div className="pt-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label font-normal text-ink-soft">
            {finished ? (error ? "The audit stopped" : "Audited just now") : "Being audited now"}
          </p>
          <h1 className="display-2 mt-1">Your answer</h1>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="label min-h-10 rounded-full border border-ink px-4 transition-colors hover:bg-ink hover:text-sheet"
        >
          {finished ? "Audit another answer" : "Stop"}
        </button>
      </div>
      {error && <p className="label mb-6 font-normal text-unverified">{error}</p>}
      {!finished && events.length === 0 && (
        <p className="label mb-6 font-normal text-ink-soft">
          <span className="animate-pulse">Starting…</span> If nobody has used the site for a while,
          the server takes about 15 seconds to wake up.
        </p>
      )}
      <AuditDesk
        events={events}
        time={Number.POSITIVE_INFINITY}
        report={report}
        strip={liveAuditItems(events, finished)}
        caption="Your answer, as pasted"
      />
    </div>
  );
}
