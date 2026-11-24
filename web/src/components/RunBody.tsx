"use client";

import { useState } from "react";
import { ClaimList } from "@/components/ClaimList";
import { SourcePane } from "@/components/SourcePane";
import type { View } from "@/lib/replay";

/** Claims on the left, the evidence for the chosen claim on the right. Used live and in replay. */
export function RunBody({ view, canCheck }: { view: View; canCheck: boolean }) {
  const [selected, setSelected] = useState(0);
  const index = selected < view.claims.length ? selected : 0;
  const claim = view.claims[index] ?? null;

  return (
    <section className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="label text-ink-soft">Claims</h2>
          <p className="label text-ink-faint tabular-nums">
            {view.sources.length > 0 &&
              `${view.sources.length} pages read · ${view.skipped.length} could not be used`}
          </p>
        </div>
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
      </div>
      <div className="lg:sticky lg:top-8 lg:self-start">
        <h2 className="label mb-3 text-ink-soft">Source</h2>
        <SourcePane claim={claim} index={index} canCheck={canCheck} />
      </div>
    </section>
  );
}

/** Before any claim exists: show what the run has really produced so far. */
function Waiting({ view }: { view: View }) {
  if (view.finished) {
    return (
      <p className="py-6 text-ink-soft">
        {view.sources.length === 0
          ? "No page could be read, so there is nothing to quote."
          : "The pages that were read did not support any claim."}
      </p>
    );
  }
  if (view.queries.length === 0) {
    return <p className="py-6 text-sm text-ink-faint">Planning what to search for…</p>;
  }
  return (
    <div className="space-y-6 py-4">
      <div>
        <p className="label mb-2 text-ink-faint">Searching for</p>
        <ul className="space-y-1.5 font-mono text-[0.8125rem] text-ink-soft">
          {view.queries.map((query) => (
            <li key={query}>{query}</li>
          ))}
        </ul>
      </div>
      {view.sources.length > 0 && (
        <div>
          <p className="label mb-2 text-ink-faint">Reading</p>
          <p className="font-mono text-[0.8125rem] leading-relaxed text-ink-soft">
            {view.sources.map((s) => s.host).join("  ·  ")}
          </p>
        </div>
      )}
    </div>
  );
}
