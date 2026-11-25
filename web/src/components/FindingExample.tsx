"use client";

import { useState } from "react";
import { AuditEvidence } from "@/components/AuditEvidence";
import { AuditSheet } from "@/components/AuditSheet";
import { AuditTally } from "@/components/AuditTally";
import { type AuditReport, sentencesOf } from "@/lib/audit";

type Props = { report: AuditReport; claimIndex: number; caption: string };

/** One answer from the real-world audit, drawn from its saved report, with one claim open. */
export function FindingExample({ report, claimIndex, caption }: Props) {
  const sentences = sentencesOf(report.claims);
  const chosen = report.claims[claimIndex];
  const start = sentences.findIndex((s) => s.claims.includes(chosen));
  const [selected, setSelected] = useState<number | null>(start >= 0 ? start : null);
  const firstNumber =
    selected === null ? 1 : sentences.slice(0, selected).reduce((n, s) => n + s.claims.length, 1);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)] 2xl:grid-cols-[minmax(0,1fr)_minmax(24rem,32rem)]">
      <div className="min-w-0">
        <AuditSheet
          text={report.answer_text}
          sentences={sentences}
          judged
          selected={selected}
          onSelect={setSelected}
          caption={caption}
        >
          <AuditTally claims={report.claims} judged card={report.scorecard} />
        </AuditSheet>
      </div>
      <aside className="lg:sticky lg:top-6 lg:self-start" aria-label="Evidence">
        <AuditEvidence
          sentence={selected === null ? null : (sentences[selected] ?? null)}
          firstNumber={firstNumber}
          judged
          onClose={() => setSelected(null)}
        />
      </aside>
    </div>
  );
}
