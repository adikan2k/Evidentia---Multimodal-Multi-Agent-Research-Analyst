import Link from "next/link";
import { caught, fullyBacked, nastyTotals, product, system } from "@/lib/evals";

/** What was measured, and what it does not do. Numbers come from the eval result files. */
export function Facts() {
  const nasty = nastyTotals();
  const ours = fullyBacked(product).value.toFixed(3);
  const plain = fullyBacked("baseline").value.toFixed(3);
  const facts = [
    {
      value: `${system(product).evidenceChars}`,
      label: "characters to read to check a claim",
      note: `Plain RAG points at a passage of ${system("baseline").evidenceChars}.`,
    },
    {
      value: `${caught.flagged} of ${caught.n}`,
      label: "deliberately broken claims caught",
      note: "By a checker that sees only the claim and the quote.",
    },
    {
      value: `${nasty.passed} of ${nasty.trials}`,
      label: "hostile-page trials passed",
      note: "Hidden instructions, a paywall, two pages that disagree.",
    },
  ];

  return (
    <section className="mt-28 border-t border-ink pt-10">
      <div className="grid gap-12 lg:grid-cols-[18rem_1fr]">
        <h2 className="font-serif text-4xl leading-tight tracking-tight">What was measured</h2>
        <div>
          <div className="grid gap-10 sm:grid-cols-3">
            {facts.map((fact) => (
              <div key={fact.label}>
                <p className="font-serif text-5xl leading-none tracking-tight">{fact.value}</p>
                <p className="mt-3 text-sm font-medium">{fact.label}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-soft">{fact.note}</p>
              </div>
            ))}
          </div>
          <p className="mt-12 max-w-2xl text-lg leading-relaxed text-ink-soft">
            <span className="text-ink">It is not more accurate than plain RAG.</span> On the same
            questions it scored {ours} against {plain}, a gap inside the noise. What it gives you
            is evidence short enough to read, and a check that catches a claim when it is wrong.
          </p>
          <Link
            href="/evals"
            className="label mt-6 inline-block border-b border-ink pb-0.5 hover:opacity-70"
          >
            All the numbers, including the unflattering ones →
          </Link>
        </div>
      </div>
    </section>
  );
}
