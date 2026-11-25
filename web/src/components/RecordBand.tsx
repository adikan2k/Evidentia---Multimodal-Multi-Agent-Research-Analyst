import Link from "next/link";
import { auditorAccuracy } from "@/lib/evals";
import { firstHandCheck, type HandCheck, pct, secondHandCheck } from "@/lib/findings";
import { SHELL } from "@/lib/site";

// The one place the page changes colour (D-053): the auditor's own record, on ink. Every figure is
// read from the site's data file, which `python -m evals report` writes from `evals/results/`.

function Stat({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="border-t border-sheet/25 pt-5">
      <p className="text-[clamp(3rem,2rem+3vw,5rem)] leading-none font-semibold tracking-[-0.04em] tabular-nums">
        {value}
      </p>
      <p className="mt-4 font-medium">{label}</p>
      <p className="mt-1.5 leading-relaxed text-sheet/75">{note}</p>
    </div>
  );
}

type Check = { name: string; short: string; check: HandCheck };

/** Both hand checks on one track, with the bar drawn where it was set, before any label. */
function ChecksTrack({ checks }: { checks: Check[] }) {
  const bar = checks[0].check.rule.flags_upheld_needed_both_tools;
  const at = (x: number) => `${x * 100}%`;
  return (
    <figure className="mt-8">
      <div className="relative h-28" role="img" aria-label={checks
        .map(({ name, check }) => `${name}: ${pct(check.flags_upheld.both_tools.share, 0)} of flags upheld`)
        .join("; ") + `. The bar is ${pct(bar, 0)}.`}>
        {/* The axis, 0 to 100%. */}
        <div className="absolute inset-x-0 top-16 h-px bg-sheet/30" />
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <span key={tick} className="data absolute top-[4.6rem] -translate-x-1/2 text-sheet/65" style={{ left: at(tick) }}>
            {pct(tick, 0)}
          </span>
        ))}
        {/* The bar, fixed before any label. */}
        <div className="absolute top-0 h-[4.25rem] border-l-2 border-dashed border-marker" style={{ left: at(bar) }} />
        {/* Written to the left of the line, so it never runs off the right edge. */}
        <span className="label absolute top-0 pr-2 text-right whitespace-nowrap text-marker" style={{ right: at(1 - bar) }}>
          The bar: {pct(bar, 0)}, set before any label
        </span>
        {checks.map(({ name, short, check }, index) => {
          const s = check.flags_upheld.both_tools;
          const top = index === 0 ? "top-[1.9rem]" : "top-[3.1rem]";
          return (
            <div key={name}>
              {/* Each dot is named where it sits, so the reader needs no legend. */}
              <span
                className={`label absolute -translate-x-full pr-3 font-normal whitespace-nowrap text-sheet/80 ${top} -translate-y-[0.2rem]`}
                style={{ left: at(s.ci_low ?? s.share ?? 0) }}
              >
                {short}
              </span>
              {s.ci_low !== null && s.ci_high !== null && (
                <div
                  className={`absolute h-0.5 bg-sheet/45 ${top} translate-y-[0.3rem]`}
                  style={{ left: at(s.ci_low), width: at(s.ci_high - s.ci_low) }}
                />
              )}
              <span
                className={`absolute size-3.5 -translate-x-1/2 rounded-full bg-sheet ring-2 ring-ink ${top}`}
                style={{ left: at(s.share ?? 0) }}
              />
            </div>
          );
        })}
      </div>
      <figcaption className="label mt-6 grid gap-1.5 font-normal text-sheet/75 sm:grid-cols-2">
        {checks.map(({ name, check }) => {
          const s = check.flags_upheld.both_tools;
          return (
            <span key={name}>
              <span className="font-medium text-sheet">{name}:</span> {pct(s.share, 0)} of flags upheld,{" "}
              {s.hits} of {s.n}.
            </span>
          );
        })}
        <span className="sm:col-span-2">The lines are 95% intervals.</span>
      </figcaption>
    </figure>
  );
}

export function RecordBand() {
  const checks: Check[] = [
    ...(firstHandCheck ? [{ name: "First check", short: "First", check: firstHandCheck }] : []),
    ...(secondHandCheck
      ? [{ name: "Second check, after the fix", short: "Second", check: secondHandCheck }]
      : []),
  ];
  const latest = checks[checks.length - 1]?.check;

  return (
    <section aria-labelledby="record-title" className="bg-ink text-sheet">
      <div className={`${SHELL} grid gap-x-20 gap-y-14 py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:py-28`}>
        <div>
          <p className="label text-sheet/75">The auditor&apos;s own record</p>
          <h2 id="record-title" className="display-2 mt-4 max-w-[30rem]">
            It is measured before it is trusted.
          </h2>
          <p className="mt-6 max-w-[34rem] leading-relaxed text-sheet/80">
            Against {auditorAccuracy.rows.toLocaleString("en")} claims that people labelled, and
            against a person checking its verdicts on real answers, blind. Where it fell short, the
            site says so.
          </p>
          <p className="label mt-8 flex flex-wrap gap-x-6 gap-y-2">
            <Link href="/evals" className="underline underline-offset-4 hover:text-marker">
              Every measurement
            </Link>
            <Link href="/findings" className="underline underline-offset-4 hover:text-marker">
              The hand checks, in full
            </Link>
          </p>
        </div>

        <div>
          <div className="grid gap-10 sm:grid-cols-2">
            <Stat
              value={pct(auditorAccuracy.flags.value, 0)}
              label="of its flags are right"
              note={`On the benchmark. A flag says a claim is not on its page, or contradicted. 95% interval ${pct(auditorAccuracy.flags.ci_low, 0)} to ${pct(auditorAccuracy.flags.ci_high, 0)}.`}
            />
            <Stat
              value={pct(auditorAccuracy.supported.value, 0)}
              label="of its “supported” marks are right"
              note={`On the benchmark. 95% interval ${pct(auditorAccuracy.supported.ci_low, 0)} to ${pct(auditorAccuracy.supported.ci_high, 0)}.`}
            />
          </div>
          {latest && (
            <div className="mt-14">
              <p className="font-medium">
                On real answers, its flags have not yet cleared the bar.
              </p>
              <ChecksTrack checks={checks} />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
