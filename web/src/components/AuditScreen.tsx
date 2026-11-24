"use client";

import { useMemo, useState } from "react";
import { AuditAnswer } from "@/components/AuditAnswer";
import { AuditEvidence } from "@/components/AuditEvidence";
import { AuditScorecard } from "@/components/AuditScorecard";
import { PipelineStrip, replayItems, type StripItem } from "@/components/PipelineStrip";
import { Transport } from "@/components/Transport";
import {
  type AuditEvent,
  type AuditReport,
  auditSteps,
  type RecordedAudit,
  auditViewAt,
  liveAuditItems,
  sentencesOf,
} from "@/lib/audit";
import { usePlayback } from "@/lib/usePlayback";

type Body = {
  events: AuditEvent[];
  time: number;
  report: AuditReport | null;
  strip: StripItem[];
  controls?: React.ReactNode;
};

/** The answer with its claims marked, the evidence pane, and the scorecard. */
function AuditBody({ events, time, report, strip, controls }: Body) {
  const view = auditViewAt(events, time);
  const claims = report && view.finished ? report.claims : view.claims;
  const judged = view.judged || (report !== null && view.finished);
  const sentences = sentencesOf(claims);
  const [selected, setSelected] = useState<number | null>(null);
  const firstNumber =
    selected === null ? 1 : sentences.slice(0, selected).reduce((n, s) => n + s.claims.length, 1);

  return (
    <>
      <section className="mt-8 border-y border-rule py-6">
        <PipelineStrip items={strip} />
        {controls && <div className="mt-5">{controls}</div>}
      </section>
      <div className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div>
          <AuditAnswer
            text={view.answerText}
            sentences={sentences}
            judged={judged}
            selected={selected}
            onSelect={setSelected}
          />
          {view.notRead.length > 0 && (
            <p className="label mt-6 text-ink-faint">
              Not read:{" "}
              {view.notRead.map((p) => `${p.host} (${p.reason})`).join(" · ")}
            </p>
          )}
        </div>
        <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
          <AuditEvidence
            sentence={selected === null ? null : (sentences[selected] ?? null)}
            firstNumber={firstNumber}
            judged={judged}
          />
          <AuditScorecard card={report && view.finished ? report.scorecard : null} />
        </div>
      </div>
    </>
  );
}

/** A recorded audit, replayed on the timings it really had. */
export function RecordedAuditScreen({ audit }: { audit: RecordedAudit }) {
  const last = audit.events[audit.events.length - 1];
  const duration = (last?.t ?? 0) + 1.5;
  const playback = usePlayback(duration);
  const steps = useMemo(() => auditSteps(audit.events), [audit]);
  const view = auditViewAt(audit.events, playback.time);
  const made = new Date(audit.answer.made_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div>
      <p className="label text-ink-faint">
        Answer by {audit.answer.model} with {audit.answer.tool}, {made} · checked by Evidentia
      </p>
      <h2 className="mt-3 max-w-4xl font-serif text-4xl leading-[1.08] tracking-tight md:text-5xl">
        {audit.question}
      </h2>
      <AuditBody
        events={audit.events}
        time={playback.time}
        report={audit.report}
        strip={replayItems(steps, playback.time)}
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
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <p className="label text-ink-faint">
          Your answer · {finished ? (error ? "stopped" : "checked") : "being checked live"}
        </p>
        <button
          type="button"
          onClick={onClose}
          className="label border-b border-ink-faint pb-0.5 text-ink-soft hover:border-ink hover:text-ink"
        >
          {finished ? "Back" : "Stop"}
        </button>
      </div>
      {error && <p className="mt-4 text-sm text-unverified">{error}</p>}
      <AuditBody
        events={events}
        time={Number.POSITIVE_INFINITY}
        report={report}
        strip={liveAuditItems(events, finished)}
      />
    </div>
  );
}
