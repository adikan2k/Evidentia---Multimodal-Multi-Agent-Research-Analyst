import type { Metadata } from "next";
import { IntervalChart } from "@/components/IntervalChart";
import { SiteHeader } from "@/components/SiteHeader";
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

export const metadata: Metadata = {
  title: "Evals · Evidentia",
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

function Tile({ value, label, note }: { value: string; label: string; note: string }) {
  return (
    <div className="border-t border-ink pt-4">
      <p className="font-serif text-5xl leading-none tracking-tight">{value}</p>
      <p className="mt-3 text-sm font-medium text-ink">{label}</p>
      <p className="mt-1 text-sm leading-relaxed text-ink-soft">{note}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-20 grid gap-x-12 gap-y-6 lg:grid-cols-[18rem_1fr]">
      <h2 className="font-serif text-3xl leading-tight tracking-tight">{title}</h2>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="label border-b border-ink text-ink-soft">
            {head.map((cell) => (
              <th key={cell} className="py-2 pr-6 font-normal">
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
                  className={`py-2.5 pr-6 ${index === 0 ? "text-ink" : "font-mono tabular-nums text-ink-soft"}`}
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
  const interval = (s: { value: number; ci_low: number; ci_high: number }) =>
    `${s.value.toFixed(3)} (${s.ci_low.toFixed(3)}–${s.ci_high.toFixed(3)})`;

  return (
    <div className="mx-auto max-w-[78rem] px-6 pb-28 pt-8 md:px-10">
      <SiteHeader />
      <p className="label text-ink-faint">Evals</p>
      <h1 className="mt-3 max-w-4xl font-serif text-5xl leading-[1.05] tracking-tight md:text-6xl">
        It is not more accurate than plain RAG. Here is what it does do.
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-soft">
        Every number on this page is read from a result file in the repository. The questions run
        against {retrieval.corpus.pages} saved pages, mostly Wikipedia, which are cleaner than the
        open web, so these scores are likely kinder than real use.
      </p>

      <div className="mt-14 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          value={`${shipped.value.toFixed(3)}`}
          label="of its backed claims are fully backed"
          note={`Plain RAG scores ${baseline.value.toFixed(3)}. The gap is inside the noise.`}
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
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ink-soft">
          On clean pages a strong writer rarely invents anything, so there is little for a checker
          to catch. What Evidentia adds is not accuracy. It shows a short exact quote where plain
          RAG shows a passage, and it costs about {costRatio} times as much per question.
        </p>
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
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ink-soft">
          {caught.n} claims were broken on purpose and paired with real quotes. The table counts how
          many each checker refused to pass as supported. No person has labelled these pairs, so
          there is no agreement-with-a-human figure.
        </p>
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
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ink-soft">
          The reranker earns its place. Keyword search does not: fusing it with dense search
          scored lower than dense search alone, and adds nothing once the reranker is on. So it is
          switched off.
        </p>
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
        <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ink-soft">
          {unanswerableCount} easy trivia questions whose answers are nowhere in the saved pages. This was the
          test expected to separate the systems. It did not: told to use only the passages,
          today&apos;s models mostly do.
        </p>
      </Section>

      <div id="auditor" className="scroll-mt-8">
        <Section title="The auditor, against people's labels">
          <Table
            head={["System", "Flags right", "Supported right", "Claims with a verdict"]}
            rows={[
              [
                "Two judges (as shipped)",
                interval(pooled.two_judges.partial_as_its_own_verdict.flag_precision),
                interval(pooled.two_judges.supported_precision),
                pooled.two_judges.coverage.value.toFixed(3),
              ],
              [
                "Quote judge alone",
                pooled.quote_judge_alone.flag_precision.value.toFixed(3),
                pooled.quote_judge_alone.supported_precision.value.toFixed(3),
                "1.000",
              ],
              [
                "Page judge alone",
                pooled.page_judge_alone.flag_precision.value.toFixed(3),
                pooled.page_judge_alone.supported_precision.value.toFixed(3),
                "1.000",
              ],
            ]}
          />
          <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ink-soft">
            {pooled.rows.toLocaleString()} rows of LLM-AggreFact, each a claim, a document and a
            person&apos;s label, none used to tune the auditor. A claim gets a verdict only when a
            judge that sees exact quotes and a judge that sees the page agree. A finish line set
            before the test (flags right 0.80, supported right 0.93) was missed on the 550 test rows
            alone ({test2.two_judges.partial_as_its_own_verdict.flag_precision.value.toFixed(3)} and{" "}
            {test2.two_judges.supported_precision.value.toFixed(3)}). Three samples of 550 rows
            differ by about as much as any change tried, so the pooled figures are the better
            estimate. Partial is its own verdict and never counted as a failure.
          </p>
        </Section>
      </div>

      <Section title="What was not done">
        <ul className="max-w-2xl space-y-3 leading-relaxed text-ink-soft">
          <li>No person has checked the checker. Its labels were compared with another model only.</li>
          <li>The judge is a model from the same family as the writer and the checker.</li>
          <li>The gold passages for the search test were chosen by a model, then verified word for word by code.</li>
          <li>Nothing here was measured on the open web, where pages are messier.</li>
        </ul>
      </Section>
    </div>
  );
}
