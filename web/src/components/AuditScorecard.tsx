import Link from "next/link";
import { auditorAccuracy } from "@/lib/evals";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** How often the auditor itself is right. Every figure is read from the results files. */
export function AuditAccuracy({ className = "" }: { className?: string }) {
  const { flags, supported, coverage, rows } = auditorAccuracy;
  const facts = [
    {
      value: pct(flags.value),
      range: `${pct(flags.ci_low)} to ${pct(flags.ci_high)}`,
      label: "of flagged claims really are unsupported",
    },
    {
      value: pct(supported.value),
      range: `${pct(supported.ci_low)} to ${pct(supported.ci_high)}`,
      label: "of supported claims really are supported",
    },
    {
      value: pct(1 - coverage.value),
      range: null,
      label: "of claims go to a person instead of getting a verdict",
    },
  ];
  return (
    <section className={`rounded-[3px] border border-rule p-5 md:p-6 ${className}`}>
      <h3 className="label text-ink">How often is the auditor right?</h3>
      <p className="label mt-1.5 font-normal text-ink-soft">
        Measured on {rows.toLocaleString()} claims that people labelled, none of them used to tune it.
      </p>
      <dl className="mt-4 space-y-3.5">
        {facts.map((fact) => (
          <div key={fact.label} className="grid grid-cols-[4.25rem_1fr] items-baseline gap-x-3">
            <dt className="text-2xl font-semibold tracking-tight tabular-nums">{fact.value}</dt>
            <dd className="label font-normal text-ink-soft">
              {fact.label}
              {fact.range && <span className="data ml-1.5 text-ink-faint normal-case">({fact.range})</span>}
            </dd>
          </div>
        ))}
      </dl>
      <Link
        href="/evals#auditor"
        className="label mt-4 inline-flex min-h-10 items-center text-ink underline underline-offset-4"
      >
        How this was measured
      </Link>
    </section>
  );
}
