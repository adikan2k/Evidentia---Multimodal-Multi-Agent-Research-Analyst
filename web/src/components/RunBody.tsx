"use client";

import { useState } from "react";
import { ClaimList } from "@/components/ClaimList";
import { PipelineStrip, type StripItem } from "@/components/PipelineStrip";
import { SourcePane } from "@/components/SourcePane";
import type { View } from "@/lib/replay";

type Props = { view: View; canCheck: boolean; strip: StripItem[]; controls?: React.ReactNode };

/**
 * The desk for a research run: the steps in a rail, the claims on the sheet, and the evidence
 * for the chosen claim on the right. Used live and in replay.
 */
export function RunBody({ view, canCheck, strip, controls }: Props) {
  const [selected, setSelected] = useState(0);
  const index = selected < view.claims.length ? selected : 0;
  const claim = view.claims[index] ?? null;

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)] 2xl:grid-cols-[14rem_minmax(0,1fr)_minmax(22rem,29rem)]">
      <aside className="lg:col-span-2 2xl:col-span-1" aria-label="Steps of the run">
        <div className="2xl:sticky 2xl:top-6">
          <h3 className="data mb-3 text-ink-faint">Steps</h3>
          <PipelineStrip items={strip} />
          {controls && <div className="mt-4 border-t border-rule pt-4">{controls}</div>}
        </div>
      </aside>

      <article className="sheet min-w-0">
        <header className="label flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-5 py-3 text-ink-soft md:px-8">
          <span>The answer, one claim at a time</span>
          <span className="data text-ink-faint normal-case">
            {view.sources.length > 0 &&
              `${view.sources.length} pages read · ${view.skipped.length} could not be used`}
          </span>
        </header>
        {view.claims.length === 0 ? (
          <Waiting view={view} />
        ) : (
          <ClaimList
            claims={view.claims}
            firstDraft={view.firstDraft}
            selected={index}
            onSelect={setSelected}
          />
        )}
      </article>

      <aside className="lg:sticky lg:top-6 lg:self-start" aria-label="Evidence">
        <SourcePane claim={claim} index={index} canCheck={canCheck} />
      </aside>
    </section>
  );
}

/** Before any claim exists: show what the run has really produced so far. */
function Waiting({ view }: { view: View }) {
  if (view.finished) {
    return (
      <p className="px-5 py-8 text-ink-soft md:px-8">
        {view.sources.length === 0
          ? "No page could be read, so there is nothing to quote."
          : "The pages that were read did not support any claim."}
      </p>
    );
  }
  if (view.queries.length === 0) {
    return <p className="label px-5 py-8 font-normal text-ink-soft md:px-8">Planning what to search for…</p>;
  }
  return (
    <div className="space-y-6 px-5 py-8 md:px-8">
      <div>
        <p className="label mb-2 text-ink">Searching for</p>
        <ul className="space-y-1.5 font-mono text-[0.8125rem] text-ink-soft">
          {view.queries.map((query) => (
            <li key={query}>{query}</li>
          ))}
        </ul>
      </div>
      {view.sources.length > 0 && (
        <div>
          <p className="label mb-2 text-ink">Reading</p>
          <p className="font-mono text-[0.8125rem] leading-relaxed text-ink-soft">
            {view.sources.map((s) => (s.kind === "pdf" ? `${s.host} (PDF)` : s.host)).join("  ·  ")}
          </p>
        </div>
      )}
    </div>
  );
}
