import Link from "next/link";
import { type AuditLabel, LABEL_TEXT, LABEL_TONE, type Scorecard } from "@/lib/audit";
import { auditorAccuracy } from "@/lib/evals";

const ORDER: AuditLabel[] = [
  "contradicted",
  "not_found",
  "partial",
  "needs_human",
  "supported",
  "dead_link",
  "unchecked",
  "citation_unread",
  "uncited",
];

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** What the audit found, and next to it how often such findings are right. */
export function AuditScorecard({ card }: { card: Scorecard | null }) {
  const { flags, supported, coverage, rows } = auditorAccuracy;
  return (
    <aside className="space-y-6">
      {card && (
        <section className="rounded-lg border border-rule bg-white/60 p-6">
          <p className="label text-ink-faint">What the audit found</p>
          {card.failed_share_of_verdicts !== null ? (
            <p className="mt-2 font-serif text-3xl leading-tight">
              {card.failed_citations} of {card.claims_with_a_verdict} claims fail their citation outright
            </p>
          ) : (
            <p className="mt-2 font-serif text-2xl leading-tight">No claim could be given a verdict</p>
          )}
          <p className="mt-2 text-sm text-ink-soft">
            Out of {card.claims} claims. A failure is a claim the cited page does not state, or
            contradicts. Partly backed claims are counted apart, never as failures.
          </p>
          <ul className="mt-5 space-y-1.5">
            {ORDER.filter((l) => card.labels[l] > 0).map((label) => (
              <li key={label} className="flex items-baseline justify-between gap-4 text-sm">
                <span className={LABEL_TONE[label]}>{LABEL_TEXT[label]}</span>
                <span className="tabular-nums text-ink">{card.labels[label]}</span>
              </li>
            ))}
          </ul>
          <p className="label mt-5 border-t border-rule pt-3 text-ink-faint">
            {card.pages_read} of {card.pages_cited} cited pages read · cost ${card.usd.toFixed(4)}
          </p>
        </section>
      )}
      <section className="rounded-lg border border-rule p-6">
        <p className="label text-ink-faint">How often is this right?</p>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Measured on {rows.toLocaleString()} claims that people labelled (LLM-AggreFact), none
          used to tune the auditor:
        </p>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-ink">A flagged claim really is unsupported</dt>
            <dd className="tabular-nums text-ink-soft">
              {pct(flags.value)} of the time ({pct(flags.ci_low)} to {pct(flags.ci_high)})
            </dd>
          </div>
          <div>
            <dt className="text-ink">A supported claim really is supported</dt>
            <dd className="tabular-nums text-ink-soft">
              {pct(supported.value)} of the time ({pct(supported.ci_low)} to {pct(supported.ci_high)})
            </dd>
          </div>
          <div>
            <dt className="text-ink">Claims sent to a human instead</dt>
            <dd className="tabular-nums text-ink-soft">{pct(1 - coverage.value)}</dd>
          </div>
        </dl>
        <Link
          href="/evals#auditor"
          className="label mt-5 inline-block border-b border-ink-faint pb-0.5 text-ink-soft hover:border-ink hover:text-ink"
        >
          How this was measured
        </Link>
      </section>
    </aside>
  );
}
