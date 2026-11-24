"use client";

import { Mark } from "@/components/Mark";
import {
  type AuditClaim,
  type AuditLabel,
  LABEL_FILL,
  LABEL_MARK,
  LABEL_MEANING,
  LABEL_ORDER,
  LABEL_TEXT,
  LABEL_TONE,
  type Scorecard,
} from "@/lib/audit";

type Props = { claims: AuditClaim[]; judged: boolean; card: Scorecard | null };

/**
 * The auditor's tally, across the foot of the sheet: one bar split by verdict, then each
 * verdict with its mark, its name and its count. It doubles as the legend for the marks.
 */
export function AuditTally({ claims, judged, card }: Props) {
  const total = claims.length;
  const counts = new Map<AuditLabel, number>();
  if (judged) {
    for (const claim of claims) {
      if (claim.label) counts.set(claim.label, (counts.get(claim.label) ?? 0) + 1);
    }
  }
  const present = LABEL_ORDER.filter((label) => (counts.get(label) ?? 0) > 0);
  const failed = (counts.get("contradicted") ?? 0) + (counts.get("not_found") ?? 0);
  const withVerdict = failed + (counts.get("supported") ?? 0) + (counts.get("partial") ?? 0);

  return (
    <footer className="border-t border-rule px-5 py-6 md:px-8">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 className="display-3">
          {!judged && (total ? `${total} claims, being checked` : "Waiting for the claims")}
          {judged && withVerdict > 0 && `${failed} of ${withVerdict} checked claims fail their citation`}
          {judged && withVerdict === 0 && "No claim could be given a verdict"}
        </h3>
        {card && (
          <p className="data text-ink-faint">
            {card.pages_read} of {card.pages_cited} cited pages read · ${card.usd.toFixed(4)}
          </p>
        )}
      </div>

      <div
        className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-paper-deep"
        role="img"
        aria-label={
          judged
            ? present.map((l) => `${counts.get(l)} ${LABEL_TEXT[l].toLowerCase()}`).join(", ")
            : "Verdicts not in yet"
        }
      >
        {present.map((label) => (
          <div
            key={label}
            className={`h-full origin-left border-r border-sheet transition-[width] duration-700 ease-out last:border-r-0 ${LABEL_FILL[label]}`}
            style={{ width: `${((counts.get(label) ?? 0) / total) * 100}%` }}
          />
        ))}
      </div>

      {judged && (
        <ul className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2 2xl:grid-cols-3">
          {present.map((label) => (
            <li key={label} className="flex gap-2.5">
              <Mark kind={LABEL_MARK[label]} className={`mt-0.5 text-[1.1rem] ${LABEL_TONE[label]}`} />
              <p className="label">
                <span className={LABEL_TONE[label]}>
                  {counts.get(label)} {LABEL_TEXT[label].toLowerCase()}
                </span>
                <span className="mt-0.5 block font-normal text-ink-soft">{LABEL_MEANING[label]}</span>
              </p>
            </li>
          ))}
        </ul>
      )}
    </footer>
  );
}
