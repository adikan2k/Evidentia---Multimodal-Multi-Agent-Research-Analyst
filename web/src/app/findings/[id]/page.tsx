import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { FindingExample } from "@/components/FindingExample";
import { Mark } from "@/components/Mark";
import { LABEL_MARK, LABEL_TEXT, LABEL_TONE } from "@/lib/audit";
import { firstHandCheck, pct, TOOL_MODEL, TOOL_NAME, withheld } from "@/lib/findings";
import { exampleAnswer, exampleIndex } from "@/lib/findingsFiles";
import { SHELL } from "@/lib/site";

// One address per example on the findings page (D-048).

export async function generateStaticParams() {
  return (await exampleIndex()).examples.map((x) => ({ id: x.id }));
}

export async function generateMetadata({ params }: PageProps<"/findings/[id]">): Promise<Metadata> {
  const { id } = await params;
  const example = (await exampleIndex()).examples.find((x) => x.id === id);
  if (!example) return {};
  const title = `${TOOL_NAME[example.tool]}: ${LABEL_TEXT[example.label].toLowerCase()}`;
  const description = `“${example.claim}” An example from Evidentia's real-world audit.`;
  const images = ["/opengraph-image"];
  return {
    title,
    description,
    openGraph: { title, description, siteName: "Evidentia", type: "article", images },
    twitter: { card: "summary_large_image", title, description, images },
  };
}

async function Example({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const example = (await exampleIndex()).examples.find((x) => x.id === id);
  if (!example) notFound();
  const answer = await exampleAnswer(example.tool, example.question);
  const asked = answer.answer.made_at
    ? new Date(answer.answer.made_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
    : null;

  return (
    <div className={`${SHELL} pt-10`}>
      <p className="label">
        <Link
          href={withheld ? "/findings" : "/findings#examples"}
          className="text-ink-soft underline underline-offset-4 hover:text-ink"
        >
          Findings
        </Link>
        <span className="text-ink-faint"> / an example, {example.why}</span>
      </p>
      {withheld && firstHandCheck && (
        <p className="mt-6 max-w-[46rem] border-l-2 border-ink pl-4 leading-relaxed text-ink-soft">
          <span className="font-medium text-ink">Read this mark with care.</span> This example comes
          from the first audit, before the page reader was fixed. In a blind hand check, a person
          upheld {pct(firstHandCheck.flags_upheld.both_tools.share, 0)} of that audit&apos;s flags,
          and the comparison it came from is withheld. The evidence is below, and the cited page is
          linked: judge this one yourself.
        </p>
      )}
      <p className={`label mt-6 flex items-center gap-2 ${LABEL_TONE[example.label]}`}>
        <Mark kind={LABEL_MARK[example.label]} className="text-[1.2rem]" />
        {LABEL_TEXT[example.label]}
        {example.cited_by === "paragraph" && (
          <span className="font-normal text-ink-soft"> · cited at the end of its paragraph</span>
        )}
      </p>
      <h1 className="display-2 mt-3 max-w-[60rem]">{answer.question}</h1>
      <p className="label mt-3 mb-8 font-normal text-ink-soft">
        Answered by {TOOL_MODEL[example.tool]}
        {asked && `, on ${asked}`}. The claim this example is about is open on the right.
      </p>
      <FindingExample
        report={answer.report}
        claimIndex={example.claim_index}
        caption={`The answer from ${TOOL_NAME[example.tool]}, as audited`}
      />
    </div>
  );
}

export default function Page({ params }: PageProps<"/findings/[id]">) {
  return (
    <Suspense fallback={<p className={`${SHELL} label pt-16 font-normal text-ink-soft`}>Loading the example…</p>}>
      <Example params={params} />
    </Suspense>
  );
}
