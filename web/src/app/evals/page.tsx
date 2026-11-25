import type { Metadata } from "next";
import Link from "next/link";
import { IntervalChart } from "@/components/IntervalChart";
import { PageIndex } from "@/components/PageIndex";
import {
  caught,
  checkerModel,
  evals,
  fullyBacked,
  nastyTotals,
  product,
  SYSTEM_LABELS,
  type SystemName,
  system,
} from "@/lib/evals";
import { firstHandCheck, pct, secondHandCheck } from "@/lib/findings";
import { SHELL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Evals",
  description: "What was measured, including the results that do not flatter the project.",
};

const RETRIEVERS: Record<string, string> = {
  bm25: "Keyword only (BM25)",
  dense: "Dense only",
  hybrid: "Hybrid",
  dense_rerank: "Dense + rerank (as shipped)",
  hybrid_rerank: "Hybrid + rerank",
};
const BROKEN: Record<string, string> = {
  wrong_quote: "Given the wrong quote",
  changed_fact: "One fact changed",
  added_detail: "A detail added",
  all_built: "All broken claims",
};

type Stat = { value: number; ci_low: number; ci_high: number };
const KS = [1, 3, 5, 10] as const;
const percent = (value: number) => `${Math.round(value * 100)}%`;
const three = (value: number) => value.toFixed(3);
const range = (s: Stat) => `95% interval ${three(s.ci_low)} to ${three(s.ci_high)}.`;

function Tile({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="border-t border-ink pt-4">
      <p className="text-5xl leading-none font-semibold tracking-tight tabular-nums">{value}</p>
      <p className="mt-3 font-medium text-ink">{label}</p>
      <p className="mt-1 leading-relaxed text-ink-soft">{note}</p>
    </div>
  );
}

/** One of the page's halves: the auditor, then the research agent. */
function Part({ id, part, title, children }: { id: string; part: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="mt-24 scroll-mt-8 border-t border-ink pt-8">
      <p className="data text-ink-faint">{part}</p>
      <h2 id={`${id}-title`} className="display-2 mt-2 max-w-[52rem]">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-16 grid gap-x-16 gap-y-5 border-t border-rule pt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
      <h3 className="display-3 text-[1.5rem] lg:sticky lg:top-6 lg:self-start">{title}</h3>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Prose({ children }: { children: React.ReactNode }) {
  return <p className="mt-6 max-w-[44rem] leading-relaxed text-ink-soft">{children}</p>;
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-ink">
            {head.map((cell, index) => (
              // Two columns can share a heading ("95% interval"), so the position is part of the key.
              <th key={`${index}-${cell}`} scope="col" className="data py-2.5 pr-6 font-normal text-ink-soft">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row[0])} className="border-b border-rule">
              {row.map((cell, index) => (
                <td
                  // biome-ignore lint: cells in a row have no better key than their position
                  key={index}
                  className={`py-3 pr-6 ${index === 0 ? "text-ink" : "font-mono text-[0.875rem] tabular-nums text-ink-soft"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvalsPage() {
  const shipped = fullyBacked(product);
  const baseline = fullyBacked("baseline");
  const nasty = nastyTotals();
  const names = Object.keys(SYSTEM_LABELS) as SystemName[];
  const detection = evals.checker_agreement.error_detection_on_built_pairs;
  const retrieval = evals.retrieval;
  // Computed, not typed in: every figure in the prose below is derived from the result files.
  const costRatio = (system(product).costPerQuestion / system("baseline").costPerQuestion).toFixed(1);
  const unanswerableCount = Object.values(evals.unanswerable.systems)[0].questions;

  const pooled = evals["aggrefact_pooled-dev550b+test2_q-haiku_p-haiku"];
  const test2 = evals["aggrefact_test2_q-haiku_p-haiku"];
  const two = pooled.two_judges;
  const asShipped = two.partial_as_its_own_verdict;
  const line = pooled.finish_line.thresholds;
  const toPerson = `${Math.round((1 - two.coverage.value) * 100)}%`;
  const judges = [
    { label: "Two judges (as shipped)", stats: two, verdicts: three(two.coverage.value) },
    { label: "Quote judge alone", stats: pooled.quote_judge_alone, verdicts: "1.000" },
    { label: "Page judge alone", stats: pooled.page_judge_alone, verdicts: "1.000" },
  ];
  // Weakest first: the point of the chart is to show where the marks are least reliable.
  const datasets = Object.entries(two.per_dataset).sort((a, b) => a[1] - b[1]);
  const coverageBy = two.coverage_per_dataset as Record<string, number>;
  const checks = [
    { label: "First, before the fix", check: firstHandCheck },
    { label: "Second, after the fix", check: secondHandCheck },
  ].flatMap(({ label, check }) => (check ? [{ label, check }] : []));
  const shippedSearch = retrieval.retrievers.dense_rerank;
  // What a perfect ranking would score, given how few relevant passages each question has.
  const best = retrieval.best_possible;
  const ceiling = (k: (typeof KS)[number]) => best[`precision_at_${k}`];
  const web = evals.open_web;
  const webSystems = [
    { label: "Plain RAG, same pages", s: web.systems.open_web_baseline },
    { label: "Evidentia (as shipped)", s: web.systems.open_web_pipeline },
  ];
  const webDiff = web.accuracy_difference_from_baseline.open_web_pipeline;
  const webCostRatio = (
    web.systems.open_web_pipeline.cost_per_question_usd / web.systems.open_web_baseline.cost_per_question_usd
  ).toFixed(1);
  const agreementModels = Object.entries(evals.checker_agreement.references.second_model.models).map(
    ([model, m]) => [model, m.all as unknown as { agreement: Stat; cohen_kappa: Stat }] as const,
  );

  return (
    <div className={SHELL}>
      <header className="grid items-end gap-x-16 gap-y-8 pt-10 pb-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:pt-16">
        <div>
          <p className="label text-ink-soft">Evals</p>
          <h1 className="display-1 mt-4 max-w-[60rem]">
            The numbers, including the ones that do not flatter it.
          </h1>
          <p className="lead mt-6 max-w-[44rem]">
            Every number on this page is read from a result file in the repository. Two things
            were measured: how often the auditor&apos;s marks agree with labels that people gave,
            and what the research agent adds over plain RAG.
          </p>
        </div>
        <PageIndex
          items={[
            { href: "#auditor", text: "The auditor, against people's labels" },
            { href: "#research", text: "The research agent, against plain RAG" },
            { href: "#search", text: "Search: recall and precision at k" },
            { href: "#not-done", text: "What was not done" },
          ]}
        />
      </header>

      <Part id="auditor" part="Part 1" title="The auditor, against labels that people gave">
        <p className="lead mt-5 max-w-[44rem]">
          {pooled.rows.toLocaleString()} rows of LLM-AggreFact, each a claim, a document and a
          person&apos;s label. None was used to tune the auditor.
        </p>
        <div className="mt-12 grid gap-10 sm:grid-cols-2 xl:grid-cols-4">
          <Tile
            value={three(asShipped.flag_precision.value)}
            label="of its flags are right"
            note={`${range(asShipped.flag_precision)} A flag is a claim marked not on the page or contradicted.`}
          />
          <Tile
            value={three(asShipped.supported_precision.value)}
            label="of its supported marks are right"
            note={range(asShipped.supported_precision)}
          />
          <Tile
            value={three(two.balanced_accuracy.value)}
            label="balanced accuracy"
            note={`On the claims that got a verdict. ${range(two.balanced_accuracy)} 0.500 is a guess.`}
          />
          <Tile
            value={toPerson}
            label="of claims get no verdict"
            note="The two judges disagreed, so the claim is passed to a person."
          />
        </div>

        <Section title="On real answers: two blind hand checks">
          <Table
            head={["Hand check", "Claims", "Flags upheld", "95% interval", "Supported upheld", "Bar of 70% met"]}
            rows={checks.map(({ label, check }) => {
              const flags = check.flags_upheld.both_tools;
              const backed = check.supported_upheld.both_tools;
              return [
                label,
                check.items_checked,
                `${pct(flags.share, 0)}, ${flags.hits} of ${flags.n}`,
                `${pct(flags.ci_low, 0)} to ${pct(flags.ci_high, 0)}`,
                `${backed.hits} of ${backed.n}`,
                check.rule.met ? "Yes" : "No",
              ];
            })}
          />
          <Prose>
            The benchmark hands the auditor clean text. So Aditya checked samples of its verdicts on
            answers from two AI search tools against the live pages, blind to the tool and to the
            verdict. A flag he could not settle is left out of the share. Between the checks, the
            auditor was changed to read the whole page, not only the article. Both checks fell
            short of the bar set before any label, so the two tools are not compared.{" "}
            <Link href="/findings" className="text-ink underline underline-offset-4">
              The findings page
            </Link>{" "}
            tells the whole story.
          </Prose>
        </Section>

        <Section title="Are two judges better than one?">
          <IntervalChart
            mark="dot"
            domain={[0.5, 0.8]}
            ticks={[0.5, 0.6, 0.7, 0.8]}
            decimals={2}
            rows={judges.map(({ label, stats }) => ({
              label,
              value: stats.flag_precision.value,
              low: stats.flag_precision.ci_low,
              high: stats.flag_precision.ci_high,
            }))}
            caption="Share of flags that a person also labelled unsupported. Here a partly backed claim counts as a flag for all three, so they are compared by the same rule. Lines are 95% intervals. The axis starts at 0.50."
          />
          <div className="mt-8">
            <Table
              head={["System", "Flags right, partial as a flag", "Supported right", "Claims with a verdict"]}
              rows={judges.map(({ label, stats, verdicts }) => [
                label,
                three(stats.flag_precision.value),
                three(stats.supported_precision.value),
                verdicts,
              ])}
            />
          </div>
          <Prose>
            Not clearly. The intervals for two judges and for the page judge alone overlap. What
            agreement buys is the third column: when the judges disagree, the claim goes to a
            person instead of getting a guess. As shipped, partly backed is its own verdict and
            not a flag, which is why the figure at the top is{" "}
            {three(asShipped.flag_precision.value)} and not {three(two.flag_precision.value)}.
          </Prose>
        </Section>

        <Section title="Where it is weakest">
          <IntervalChart
            mark="dot"
            domain={[0.5, 1]}
            ticks={[0.5, 0.6, 0.7, 0.8, 0.9, 1]}
            decimals={2}
            rows={datasets.map(([name, value]) => ({
              label: name,
              value,
              detail: `A verdict on ${Math.round(coverageBy[name] * 100)}% of its claims`,
            }))}
            caption={`Balanced accuracy on the claims that got a verdict, for each of the ${datasets.length} sources of rows, ${pooled.rows / datasets.length} rows each, so every dot is rough. 0.50 is what guessing would score.`}
          />
          <Prose>
            The spread is wide. {datasets[0][0]} scores {datasets[0][1].toFixed(2)} and{" "}
            {datasets[1][0]} {datasets[1][1].toFixed(2)}, not far above a guess.{" "}
            {datasets[datasets.length - 1][0]} scores{" "}
            {datasets[datasets.length - 1][1].toFixed(2)}. The kind of text matters more than any
            change that was tried to the judges.
          </Prose>
        </Section>

        <Section title="The finish line it missed">
          <Table
            head={["Measure", "Line set before the test", "Test rows alone", "Both samples pooled"]}
            rows={[
              [
                "Flags right",
                line.flag_precision.toFixed(2),
                three(test2.two_judges.partial_as_its_own_verdict.flag_precision.value),
                three(asShipped.flag_precision.value),
              ],
              [
                "Supported right",
                line.supported_precision.toFixed(2),
                three(test2.two_judges.supported_precision.value),
                three(asShipped.supported_precision.value),
              ],
              [
                "Claims with a verdict",
                line.coverage.toFixed(2),
                three(test2.two_judges.coverage.value),
                three(two.coverage.value),
              ],
            ]}
          />
          <Prose>
            A line was set before the last test: flags right {line.flag_precision.toFixed(2)},
            supported right {line.supported_precision.toFixed(2)}. On the {test2.rows} test rows
            alone the auditor missed both. Samples of {test2.rows} rows differ from one another by
            about as much as any change that was tried, so the pooled figures are the better
            estimate, and they are the ones shown at the top. The miss stands either way.
          </Prose>
        </Section>
      </Part>

      <Part id="research" part="Part 2" title="The research agent: not more accurate than plain RAG">
        <p className="lead mt-5 max-w-[44rem]">
          The questions run against {retrieval.corpus.pages} saved pages, mostly Wikipedia, which
          are cleaner than the open web. These scores are likely kinder than real use.
        </p>
        <div className="mt-12 grid gap-10 sm:grid-cols-2 xl:grid-cols-4">
          <Tile
            value={three(shipped.value)}
            label="of its backed claims are fully backed"
            note={`Plain RAG scores ${three(baseline.value)}. The gap is inside the noise.`}
          />
          <Tile
            value={`${caught.flagged} of ${caught.n}`}
            label="deliberately broken claims caught"
            note="By the checker, which sees only the claim and the quote."
          />
          <Tile
            value={`${system(product).evidenceChars}`}
            label="characters to read to check a claim"
            note={`Plain RAG points at a passage of ${system("baseline").evidenceChars}.`}
          />
          <Tile
            value={`${nasty.passed} of ${nasty.trials}`}
            label="hostile-page trials passed"
            note="Hidden instructions, a paywall, two pages that disagree."
          />
        </div>

        <Section title="Is it more accurate? No.">
          <IntervalChart
            mark="dot"
            domain={[0.8, 1]}
            ticks={[0.8, 0.85, 0.9, 0.95, 1]}
            decimals={2}
            rows={names.map((name) => {
              const s = fullyBacked(name);
              return {
                label: SYSTEM_LABELS[name],
                value: s.value,
                low: s.ci_low,
                high: s.ci_high,
                detail: `${s.correct} of ${s.claims} claims`,
              };
            })}
            caption={`Share of the claims each system shows as backed that a separate judge (${evals.citation_accuracy.judge.split(" ")[0]}) found fully backed, on ${evals.citation_accuracy.questions} questions. Lines are 95% intervals; they all overlap. The axis starts at 0.80.`}
          />
          <div className="mt-8">
            <Table
              head={["System", "Backed claims / question", "Characters to read", "Cost / question"]}
              rows={names.map((name) => {
                const s = system(name);
                return [
                  SYSTEM_LABELS[name],
                  s.shownPerQuestion.toFixed(2),
                  s.evidenceChars,
                  `$${s.costPerQuestion.toFixed(3)}`,
                ];
              })}
            />
          </div>
          <Prose>
            On clean pages a strong writer rarely invents anything, so there is little for a
            checker to catch. What Evidentia adds is not accuracy. It shows a short exact quote
            where plain RAG shows a passage, and it costs about {costRatio} times as much per
            question.
          </Prose>
        </Section>

        <Section title="And on the open web?">
          <IntervalChart
            mark="dot"
            domain={[0.8, 1]}
            ticks={[0.8, 0.85, 0.9, 0.95, 1]}
            decimals={2}
            rows={webSystems.map(({ label, s }) => {
              const a = s.presented_as_backed.citation_accuracy;
              return {
                label,
                value: a.value,
                low: a.ci_low,
                high: a.ci_high,
                detail: `${a.correct} of ${a.claims} claims`,
              };
            })}
            caption={`Share of the claims each system shows as backed that the same judge found fully backed, on ${web.questions} questions asked on live web search. Lines are 95% intervals. The axis starts at 0.80.`}
          />
          <div className="mt-8">
            <Table
              head={["System", "Backed claims / question", "Characters to read", "Cost / question"]}
              rows={webSystems.map(({ label, s }) => [
                label,
                s.presented_as_backed.claims_per_question.mean.toFixed(2),
                s.evidence_chars_median,
                `$${s.cost_per_question_usd.toFixed(3)}`,
              ])}
            />
          </div>
          <Prose>
            {web.questions} of the questions were asked again from the start: the agent searched the
            live web and read {web.pages.pages_read} pages from {web.pages.different_sites_read}{" "}
            sites, {percent(web.pages.wikipedia_share_of_pages_read)} of them from Wikipedia.{" "}
            {web.pages.pages_not_read} more could not be read, most often because robots.txt
            disallowed it or the site refused. Plain RAG answered from the same pages. The agent
            scored {three(webDiff.mean)} higher per question, but the interval runs from{" "}
            {three(webDiff.ci_low)} to {three(webDiff.ci_high)}, so on the open web too it is not
            clearly more accurate. It costs about {webCostRatio} times as much. Search results
            change, so this run cannot be repeated exactly.
          </Prose>
        </Section>

        <Section title="Does the checker catch errors?">
          <Table
            head={["Checker model", ...Object.values(BROKEN)]}
            rows={Object.entries(detection).map(([model, kinds]) => [
              model === checkerModel ? `${model} (as shipped)` : model,
              ...Object.keys(BROKEN).map((kind) => {
                const k = kinds[kind as keyof typeof kinds];
                return `${k.flagged} of ${k.n}`;
              }),
            ])}
          />
          <Prose>
            {caught.n} claims were broken on purpose and paired with real quotes. The table counts
            how many each checker refused to pass as supported. No person has labelled these
            pairs, so there is no agreement-with-a-human figure.
          </Prose>
          <div className="mt-8">
            <Table
              head={["Checker model", "Agreement", "95% interval", "Cohen's kappa", "95% interval"]}
              rows={agreementModels.map(([model, all]) => [
                model === checkerModel ? `${model} (as shipped)` : model,
                three(all.agreement.value),
                `${three(all.agreement.ci_low)} to ${three(all.agreement.ci_high)}`,
                three(all.cohen_kappa.value),
                `${three(all.cohen_kappa.ci_low)} to ${three(all.cohen_kappa.ci_high)}`,
              ])}
            />
          </div>
          <Prose>
            Agreement with a second, stronger model on{" "}
            {evals.checker_agreement.references.second_model.pairs_labelled} claim-and-quote pairs.
            This is not a person: it says the checker is consistent with another model from the
            same family, not that either is right. Kappa corrects for agreement by chance: 0 is
            chance and 1 is perfect.
          </Prose>
        </Section>

        <Section title="Which search works?">
          <IntervalChart
            mark="bar"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            decimals={2}
            rows={Object.entries(RETRIEVERS).map(([key, label]) => {
              const m = retrieval.retrievers[key as keyof typeof retrieval.retrievers].ndcg_at_10;
              return { label, value: m.mean, low: m.ci_low, high: m.ci_high };
            })}
            caption={`nDCG at 10 on ${retrieval.questions} questions over ${retrieval.corpus.passages.toLocaleString("en")} passages. The thin line under each bar is its 95% interval.`}
          />
          <Prose>
            The reranker earns its place. Keyword search does not: fusing it with dense search
            scored lower than dense search alone, and adds nothing once the reranker is on. So it
            is switched off. Recall, precision and the rest at each cut-off are in{" "}
            <a href="#search" className="text-ink underline underline-offset-4">
              Part 3
            </a>
            .
          </Prose>
        </Section>

        <Section title="Questions the pages cannot answer">
          <Table
            head={["System", "Made no claim", "Answered from memory", "Claims shown as backed"]}
            rows={Object.entries(evals.unanswerable.systems).map(([name, s]) => [
              SYSTEM_LABELS[name.replace("unanswerable_", "") as SystemName] ?? name,
              `${s.presented_no_backed_claim} of ${s.questions}`,
              `${s.gave_the_answer_from_memory} of ${s.questions}`,
              s.claims_presented_as_backed,
            ])}
          />
          <Prose>
            {unanswerableCount} easy trivia questions whose answers are nowhere in the saved pages.
            This was the test expected to separate the systems. It did not: told to use only the
            passages, today&apos;s models mostly do.
          </Prose>
        </Section>
      </Part>

      <Part id="search" part="Part 3" title="Search: recall and precision at k">
        <p className="lead mt-5 max-w-[44rem]">
          {retrieval.questions} questions over {retrieval.corpus.passages.toLocaleString("en")}{" "}
          passages from {retrieval.corpus.pages} saved pages. A passage counts as relevant if it
          overlaps a gold snippet, checked word for word against the page. Each question has{" "}
          {retrieval.relevant_per_question.mean.toFixed(1)} relevant passages on average.
        </p>
        <div className="mt-12 grid gap-10 sm:grid-cols-2 xl:grid-cols-4">
          <Tile
            value={three(shippedSearch.recall_at_10.mean)}
            label="recall at 10"
            note={`Share of the relevant passages in the top 10, as shipped (dense + rerank). 95% interval ${three(shippedSearch.recall_at_10.ci_low)} to ${three(shippedSearch.recall_at_10.ci_high)}.`}
          />
          <Tile
            value={three(shippedSearch.precision_at_1.mean)}
            label="precision at 1"
            note="How often the first passage returned is a relevant one."
          />
          <Tile
            value={three(shippedSearch.mrr_at_10.mean)}
            label="MRR at 10"
            note="One over the rank of the first relevant passage, averaged. 1.000 means always first."
          />
          <Tile
            value={three(shippedSearch.ndcg_at_10.mean)}
            label="nDCG at 10"
            note="Rewards relevant passages more the higher they rank. 1.000 is the best order."
          />
        </div>

        <Section title="Recall at k">
          <Table
            head={["Retriever", ...KS.map((k) => `Recall@${k}`)]}
            rows={Object.entries(RETRIEVERS).map(([key, label]) => {
              const m = retrieval.retrievers[key as keyof typeof retrieval.retrievers];
              return [label, ...KS.map((k) => three(m[`recall_at_${k}`].mean))];
            }).concat([["Best possible", ...KS.map((k) => three(best[`recall_at_${k}`]))]])}
          />
          <Prose>
            Of all the passages that hold the answer, the share found in the top k. The last row
            is what a perfect ranking would score: a question with three relevant passages cannot
            have them all in the top one. The research agent reads the top 10 after reranking,
            where the shipped search finds {percent(shippedSearch.recall_at_10.mean)} of them.
          </Prose>
        </Section>

        <Section title="Precision at k">
          <Table
            head={["Retriever", ...KS.map((k) => `Precision@${k}`)]}
            rows={[
              ...Object.entries(RETRIEVERS).map(([key, label]) => {
                const m = retrieval.retrievers[key as keyof typeof retrieval.retrievers];
                return [label, ...KS.map((k) => three(m[`precision_at_${k}`].mean))];
              }),
              ["Best possible", ...KS.map((k) => three(ceiling(k)))],
            ]}
          />
          <Prose>
            Of the top k passages returned, the share that is relevant. A question has only a few
            relevant passages, so even a perfect ranking scores {three(ceiling(10))} at 10. The
            last row is that ceiling, worked out from each question&apos;s count. Read against it,
            the shipped search scores {three(shippedSearch.precision_at_10.mean)} of a possible{" "}
            {three(ceiling(10))} at 10, and puts a relevant passage first{" "}
            {percent(shippedSearch.precision_at_1.mean)} of the time.
          </Prose>
        </Section>

        <Section title="MRR and nDCG">
          <Table
            head={["Retriever", "MRR@10", "95% interval", "nDCG@10", "95% interval"]}
            rows={Object.entries(RETRIEVERS).map(([key, label]) => {
              const m = retrieval.retrievers[key as keyof typeof retrieval.retrievers];
              return [
                label,
                three(m.mrr_at_10.mean),
                `${three(m.mrr_at_10.ci_low)} to ${three(m.mrr_at_10.ci_high)}`,
                three(m.ndcg_at_10.mean),
                `${three(m.ndcg_at_10.ci_low)} to ${three(m.ndcg_at_10.ci_high)}`,
              ];
            })}
          />
          <Prose>
            Intervals are a {retrieval.interval}. The gold snippets were drafted by a model and
            then checked word for word by code. The pages are mostly Wikipedia, so these scores
            are likely kinder than the open web.
          </Prose>
        </Section>
      </Part>

      <Part id="not-done" part="Part 4" title="What was not done">
        <ul className="mt-8 grid max-w-[72rem] gap-x-16 gap-y-5 leading-relaxed text-ink-soft md:grid-cols-2">
          <li>
            <span className="font-medium text-ink">The auditor has not passed its own hand check on real answers.</span>{" "}
            Two blind checks, of {checks.map((c) => c.check.items_checked).join(" and ")} claims,
            both fell short of the bar, so the two AI tools are not compared.
          </li>
          <li>
            <span className="font-medium text-ink">Both of the auditor&apos;s judges are the same model,</span>{" "}
            so they can share a blind spot. Others were tried on the benchmark and not kept: an
            OpenAI page judge made no clear difference, and Sonnet was no better at many times the
            cost. The real-world audit was also run with the OpenAI page judge, as a check.
          </li>
          <li>
            <span className="font-medium text-ink">No person has checked the research agent&apos;s checker.</span>{" "}
            Its labels were compared with another model only, from the same family as the writer.
          </li>
          <li>
            <span className="font-medium text-ink">The search test&apos;s gold passages were chosen by a model,</span>{" "}
            then verified word for word by code.
          </li>
          <li>
            <span className="font-medium text-ink">On the open web, the research agent was asked {web.questions} questions, once.</span>{" "}
            Search results change, so that run cannot be repeated exactly, and its intervals are
            wide.
          </li>
        </ul>
      </Part>
    </div>
  );
}
