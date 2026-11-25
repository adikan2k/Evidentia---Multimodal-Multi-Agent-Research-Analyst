import type { Metadata } from "next";
import Link from "next/link";
import { LabelBars } from "@/components/LabelBars";
import { Mark } from "@/components/Mark";
import { PageIndex } from "@/components/PageIndex";
import { LABEL_MARK, LABEL_TEXT, LABEL_TONE } from "@/lib/audit";
import { auditorAccuracy } from "@/lib/evals";
import {
  askedAgainRange,
  clearOfZero,
  handCheck,
  higher,
  type Interval,
  otherJudge,
  pct,
  points,
  range,
  reask,
  realworld,
  reread,
  shipped,
  short,
  studyCost,
  TOOL_MODEL,
  TOOL_NAME,
  TOOLS,
} from "@/lib/findings";
import { exampleIndex } from "@/lib/findingsFiles";
import { REPO, SHELL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Findings",
  description:
    "Two AI search tools answered the same 100 questions. Evidentia read every page they cited and marked each claim.",
};

const DATA = `${REPO}/tree/rebuild/evals/realworld`;
const RESULTS = `${REPO}/tree/rebuild/evals/results`;
const DECISIONS = `${REPO}/blob/rebuild/docs/DECISIONS.md`;

function Reading({ title, note, values, gap }: { title: string; note: string; values: Interval[]; gap: Interval }) {
  return (
    <div className="border-t border-ink pt-4">
      <h3 className="font-medium text-ink">{title}</h3>
      <p className="label mt-1 font-normal text-ink-soft">{note}</p>
      <dl className="mt-5 grid grid-cols-2 gap-6">
        {TOOLS.map((tool, i) => (
          <div key={tool}>
            <dt className="data text-ink-faint">{TOOL_NAME[tool]}</dt>
            <dd className="mt-1 text-5xl leading-none font-semibold tracking-tight tabular-nums">
              {pct(values[i].value)}
            </dd>
            <dd className="data mt-2 text-ink-faint normal-case">{range(values[i])}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-5 leading-relaxed text-ink-soft">
        {TOOL_NAME[higher(gap)]}&apos;s is higher by{" "}
        <span className="font-medium text-ink">{points(gap)}</span>
        {clearOfZero(gap) ? "." : ", a gap that could be zero."}
      </p>
    </div>
  );
}

function HandCheckLine() {
  if (!handCheck) {
    return (
      <p>
        <span className="font-medium text-ink">No flag has been checked by a person yet.</span> A
        blind check of a sample of the verdicts is built and waiting for its labels.
      </p>
    );
  }
  const f = handCheck.flags_upheld.both_tools;
  return (
    <p>
      <span className="font-medium text-ink">
        {f.n} flags checked by hand, {pct(f.share, 0)} upheld
      </span>{" "}
      ({pct(f.ci_low, 0)} to {pct(f.ci_high, 0)}). The check was blind: no tool name and no verdict
      shown.
    </p>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-x-16 gap-y-3 border-t border-rule pt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
      <h3 className="display-3 text-[1.375rem]">{title}</h3>
      <div className="max-w-[46rem] space-y-3 leading-relaxed text-ink-soft">{children}</div>
    </section>
  );
}

export default async function FindingsPage() {
  const index = await exampleIndex();
  const withheld = handCheck !== undefined && !handCheck.rule.met;
  const uncited = (tool: (typeof TOOLS)[number]) => shipped.tools[tool].labels.uncited.share;
  const repeats = Object.entries(reask.openai_minus_claude).filter(([name]) => name.startsWith("r"));
  const heldEveryTime = [["first_ask", reask.openai_minus_claude.first_ask], ...repeats].every(
    ([, gap]) => clearOfZero(gap as Interval),
  );
  const bounds = (tool: (typeof TOOLS)[number]) => shipped.tools[tool].headline_bounds.unread_pages;
  const readAgain = (["main", "reask"] as const).reduce(
    (n, run) => ({ read: n.read + reread.runs[run].pages.read, tried: n.tried + reread.runs[run].pages.tried }),
    { read: 0, tried: 0 },
  );
  const whenWritten = new Date(realworld.generated_at).toLocaleDateString("en-GB", { month: "long", year: "numeric" });

  return (
    <div className={SHELL}>
      <header className="grid items-end gap-x-16 gap-y-8 pt-10 pb-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:pt-16">
        <div>
          <p className="label text-ink-soft">Findings · {whenWritten}</p>
          <h1 className="display-1 mt-4 max-w-[60rem]">
            Asked the same {realworld.questions} questions, two AI search tools cited very
            differently.
          </h1>
          <p className="lead mt-6 max-w-[44rem]">
            {TOOLS.map((t) => TOOL_MODEL[t]).join(", and ")}, each answered the same fixed
            questions. Evidentia read every page they cited and marked each claim, with the same
            auditor the rest of this site uses.
          </p>
        </div>
        <PageIndex
          items={[
            { href: "#result", text: "The result, read two ways" },
            { href: "#break", text: "Trying to break it" },
            { href: "#examples", text: "Examples, chosen by a rule" },
            { href: "#data", text: "The data" },
          ]}
        />
      </header>

      <section id="result" aria-labelledby="result-title" className="mt-16 scroll-mt-8 border-t border-ink pt-8">
        <h2 id="result-title" className="sr-only">
          The result
        </h2>
        <div className="grid gap-x-16 gap-y-12 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="sheet p-5 md:p-8">
            <LabelBars
              rows={TOOLS.map((tool) => ({
                name: TOOL_NAME[tool],
                detail: `${shipped.tools[tool].claims.toLocaleString("en")} claims`,
                counts: Object.fromEntries(
                  Object.entries(shipped.tools[tool].labels).map(([label, v]) => [label, v.claims]),
                ),
              }))}
            />
          </div>

          <div className="space-y-10">
            {withheld ? (
              <div className="border-t border-ink pt-4">
                <h3 className="font-medium text-ink">The comparison is withheld.</h3>
                <p className="mt-2 leading-relaxed text-ink-soft">
                  A person upheld fewer of the auditor&apos;s flags than the rule set in advance
                  needs ({pct(handCheck?.rule.flags_upheld_needed_both_tools ?? null, 0)}), so these marks
                  are not reliable enough to compare the two tools.
                </p>
              </div>
            ) : (
              <>
                <Reading
                  title="Citations that fail"
                  note="Of the claims cited in their own sentence that got a verdict, the share whose page does not say it, or says the opposite."
                  values={TOOLS.map((t) => shipped.tools[t].headline_failed_share)}
                  gap={shipped.openai_minus_claude}
                />
                <Reading
                  title="Claims verified"
                  note="Of everything each tool said, the share that a page it cited was found to back."
                  values={TOOLS.map((t) => shipped.tools[t].verified_share_of_all_claims)}
                  gap={shipped.openai_minus_claude_verified_share_of_all_claims}
                />
              </>
            )}
          </div>
        </div>

        <div className="mt-12 grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <p className="lead max-w-[44rem]">
            <span className="font-medium text-ink">They fail in different ways.</span> OpenAI cites
            most of what it says, and many of those citations do not hold. Claude&apos;s citations
            hold more often, but it leaves {pct(uncited("claude"), 0)} of its claims with no
            citation at all, against {pct(uncited("openai"), 0)} for OpenAI.
          </p>
          <div className="space-y-4 leading-relaxed text-ink-soft">
            <HandCheckLine />
            <ul className="space-y-2">
              <li>
                The auditor is right on {pct(auditorAccuracy.flags.value, 0)} of its flags, measured on{" "}
                {auditorAccuracy.rows.toLocaleString("en")} claims people labelled.{" "}
                <Link href="/evals#auditor" className="text-ink underline underline-offset-4">
                  How
                </Link>
              </li>
              <li>
                Both of its judges are Claude models ({shipped.page_judge}) judging a Claude
                product. A GPT judge was run as a check, below.
              </li>
              <li>
                One answer per question. On {reask.questions.length} questions asked{" "}
                {askedAgainRange("openai").asks} times, OpenAI&apos;s figure ran from{" "}
                {pct(askedAgainRange("openai").min, 0)} to {pct(askedAgainRange("openai").max, 0)}.
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section id="break" aria-labelledby="break-title" className="mt-24 scroll-mt-8 border-t border-ink pt-8">
        <h2 id="break-title" className="display-2">
          Trying to break it
        </h2>
        <div className="mt-10 space-y-10">
          <Block title="Another judge">
            <p>
              With OpenAI&apos;s {otherJudge.page_judge} as the page judge in place of a Claude
              model, citations that fail: OpenAI {pct(otherJudge.tools.openai.headline_failed_share.value)},
              Claude {pct(otherJudge.tools.claude.headline_failed_share.value)}, a gap of{" "}
              {points(otherJudge.openai_minus_claude)}. The Claude judge was not kinder to Claude.
            </p>
          </Block>
          <Block title="Asking again">
            <p>
              {reask.questions.length} of the questions were asked {reask.repeats} more times of
              each tool. {heldEveryTime ? "In every ask, OpenAI's citations failed more often, and no interval for the gap reached zero." : "The gap did not hold clear of zero in every ask."}{" "}
              The size did not hold: over the first ask and the repeats, OpenAI&apos;s figure ran
              from {pct(askedAgainRange("openai").min, 0)} to {pct(askedAgainRange("openai").max, 0)},
              Claude&apos;s from {pct(askedAgainRange("claude").min, 0)} to{" "}
              {pct(askedAgainRange("claude").max, 0)}. So read the figures above as
              a direction and a rough size, not as one exact rate.
            </p>
          </Block>
          <Block title="Pages that could not be read">
            <p>
              Some cited pages refused the fetcher or gave too little text, so their claims got no
              verdict. If every one had backed its claim, the failure rates would be{" "}
              {pct(bounds("openai").if_all_supported, 0)} and {pct(bounds("claude").if_all_supported, 0)}; if
              none had, {pct(bounds("openai").if_none_supported, 0)} and{" "}
              {pct(bounds("claude").if_none_supported, 0)}.
            </p>
            <p>
              Reading the thin pages again in a browser gave enough text for {readAgain.read} of{" "}
              {readAgain.tried}: most were short pages or paywalls, not pages built by scripts.
              Judging the short pages anyway, as a check, puts the gap at{" "}
              {points(short.runs.main.openai_minus_claude.with_short_pages)}. The result does not
              rest on where the line for &ldquo;too little text&rdquo; was drawn.
            </p>
          </Block>
          <Block title="Was it fair to each tool?">
            <p>
              Claude ran on its older web search tool, because the newer one returns no citation
              data an auditor can read. In the main run Claude was held to {reask.search_cap}{" "}
              searches and OpenAI was not. In the repeats both were, and no answer reached the cap:
              the most any used was {reask.tools.openai.searches.max} for OpenAI and{" "}
              {reask.tools.claude.searches.max} for Claude. So the cap cannot explain the gap.
            </p>
            <p>
              OpenAI&apos;s citations are the links it wrote into its own answers (
              {reask.openai_markers.links_the_tool_wrote_inline} of {reask.openai_markers.annotations}{" "}
              in the repeats), so the auditor read them where OpenAI put them. Many answers used no
              search at all: {reask.tools.claude.searches.answers_with_no_search} of Claude&apos;s{" "}
              {reask.tools.claude.searches.answers} and {reask.tools.openai.searches.answers_with_no_search}{" "}
              of OpenAI&apos;s {reask.tools.openai.searches.answers}. Those cite nothing.
            </p>
          </Block>
          <Block title="What it cost">
            <p>
              ${studyCost().toFixed(2)} in model and search calls for the whole study: the answers,
              both judges, the repeats and the re-reads.
            </p>
          </Block>
        </div>
      </section>

      <section id="examples" aria-labelledby="examples-title" className="mt-24 scroll-mt-8 border-t border-ink pt-8">
        <div className="grid gap-x-16 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <h2 id="examples-title" className="display-2">
            Examples
          </h2>
          <p className="max-w-[46rem] leading-relaxed text-ink-soft">
            Chosen by a rule fixed before any answer existed: every claim marked contradicted, then
            claims marked not on the cited page drawn at random with seed {index.seed}. None was
            picked by hand. Each opens with its evidence.
          </p>
        </div>
        <div className="mt-10 grid gap-x-12 gap-y-10 lg:grid-cols-2">
          {TOOLS.map((tool) => (
            <div key={tool}>
              <h3 className="data text-ink-faint">{TOOL_NAME[tool]}</h3>
              <ul className="mt-3 divide-y divide-rule border-y border-rule">
                {index.examples
                  .filter((x) => x.tool === tool)
                  .map((x) => (
                    <li key={x.id}>
                      <Link
                        href={`/findings/${x.id}`}
                        className="group grid grid-cols-[1.5rem_1fr] gap-x-3 py-4 transition-colors hover:bg-paper-deep/60"
                      >
                        <Mark kind={LABEL_MARK[x.label]} className={`mt-1 ${LABEL_TONE[x.label]}`} />
                        <span>
                          <span className="sheet-text block text-[1.0625rem] leading-snug text-ink group-hover:underline">
                            {x.claim}
                          </span>
                          <span className="label mt-1 block font-normal text-ink-soft">
                            <span className={LABEL_TONE[x.label]}>{LABEL_TEXT[x.label]}</span>
                            {x.cited_by === "paragraph" && " · cited at the end of its paragraph"} · {x.question_text}
                          </span>
                        </span>
                      </Link>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section id="data" aria-labelledby="data-title" className="mt-24 scroll-mt-8 border-t border-ink pt-8">
        <div className="grid gap-x-16 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <h2 id="data-title" className="display-2">
            The data
          </h2>
          <ul className="max-w-[46rem] space-y-3 leading-relaxed text-ink-soft">
            <li>
              <a href={DATA} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-4">
                The questions, every answer and every audit
              </a>
              , fixed and published before any answer was asked for.
            </li>
            <li>
              <a href={RESULTS} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-4">
                The result files
              </a>{" "}
              every number on this page is read from.
            </li>
            <li>
              <a href={DECISIONS} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-4">
                The decision log
              </a>
              , D-042 to D-048: the plan, what went wrong in the pilot, and each check above.
            </li>
            <li>
              <Link href="/method" className="text-ink underline underline-offset-4">
                How a claim gets its mark
              </Link>
              , and where not to trust it.
            </li>
          </ul>
        </div>
      </section>
    </div>
  );
}
