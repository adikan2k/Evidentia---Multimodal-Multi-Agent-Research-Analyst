import type { Metadata } from "next";
import Link from "next/link";
import { AuditAccuracy } from "@/components/AuditScorecard";
import { Mark } from "@/components/Mark";
import { PageIndex } from "@/components/PageIndex";
import { LABEL_MARK, LABEL_MEANING, LABEL_ORDER, LABEL_TEXT, LABEL_TONE } from "@/lib/audit";
import { auditorAccuracy, evals, nastyTotals } from "@/lib/evals";
import { REPO, SHELL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Method and limits",
  description: "How Evidentia decides each mark, and the ways those marks can be wrong.",
};

const pct = (value: number) => `${Math.round(value * 100)}%`;

export default function MethodPage() {
  // The limits are the code's own settings, written into the data file by `python -m evals report`.
  const limits = evals.auditor_limits;
  const judges = evals["aggrefact_pooled-dev550b+test2_q-haiku_p-haiku"].judges;
  const sameModel = judges.quote === judges.page;
  const nasty = nastyTotals();
  const { flags, supported, coverage, rows } = auditorAccuracy;

  const steps = [
    {
      title: "Read the citations",
      text: "Code, not a model, finds the citations: links, bare addresses, and numbered markers with a source list. A marker that matches no source is marked as a citation that could not be read, and its sentence is not judged against some other page.",
    },
    {
      title: "Split the answer into claims",
      text: `A model splits the answer into single claims, each tied to the sentence it came from. A claim takes the citations in its own sentence. If it has none, it borrows the ones at the end of its paragraph, and the audit says so. An audit covers the first ${limits.audit_max_claims} claims.`,
    },
    {
      title: "Fetch the cited pages",
      text: `Each page is fetched once, obeying robots.txt, with at most one request every ${limits.per_host_interval_s} seconds to a site. An audit reads up to ${limits.audit_max_pages} pages. A page that refuses, or gives fewer than ${limits.audit_min_page_chars.toLocaleString()} characters of text, is marked as not checked.`,
    },
    {
      title: "Two judges, apart",
      text: `The quote judge picks quotes from the page. Code checks that each is an exact run of the page's text, and a checker then rules on the claim seeing those quotes and nothing else. The page judge reads the claim against the page. For a page over ${limits.audit_page_chars.toLocaleString()} characters, both work from the passages that best match the claim.`,
    },
    {
      title: "A verdict needs both",
      text: "When the judges agree, the claim gets their mark. When they disagree, it gets no verdict: it is marked for a person, with both judges' reasons shown.",
    },
  ];

  const weak = [
    {
      title: "It checks the citation, not the truth.",
      text: "Supported means the cited page states the claim. The page itself may be wrong.",
    },
    {
      title: "Its marks are sometimes wrong.",
      text: `On ${rows.toLocaleString()} claims that people labelled, ${pct(flags.value)} of its flags and ${pct(supported.value)} of its supported marks agreed with the person. ${pct(1 - coverage.value)} of claims got no verdict.`,
    },
    {
      title: sameModel ? "Both judges are the same model." : "Both judges are language models.",
      text: sameModel
        ? `Both are ${judges.quote}. They see different things, quotes or the page, but they can share a blind spot, so their agreement is weaker evidence than a person's check.`
        : "They can share a blind spot, so their agreement is weaker evidence than a person's check.",
    },
    {
      title: "The same claim can get a different mark on another run.",
      text: "The judges are models and are not fully repeatable. This has been seen with rounded numbers, which one run called contradicted and another sent to a person.",
    },
    {
      title: "Some pages cannot be read.",
      text: "A site may refuse the fetcher or disallow it in robots.txt, and a page built in the browser by scripts gives too little text. Evidentia does not pose as a browser to get around a refusal. Those claims get no verdict.",
    },
    {
      title: "Uncited claims are not checked.",
      text: "A sentence with no citation in it or at the end of its paragraph is marked uncited and left alone.",
    },
    {
      title: "No person has checked its marks on real answers yet.",
      text: "The accuracy figures come from a benchmark of labelled claims. A blind hand check of its marks on answers from today's AI tools is built and not yet done.",
    },
    {
      title: "Hostile pages were tested on the research agent only.",
      text: `Fetched pages are passed to the models as marked data, and instructions inside them are not followed. The research agent passed ${nasty.passed} of ${nasty.trials} hostile-page trials. The auditor has not been through the same test.`,
    },
  ];

  return (
    <div className={SHELL}>
      <header className="grid items-end gap-x-16 gap-y-8 pt-10 pb-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:pt-16">
        <div>
          <p className="label text-ink-soft">Method and limits</p>
          <h1 className="display-1 mt-4 max-w-[60rem]">
            How a claim gets its mark, and how the mark can be wrong.
          </h1>
          <p className="lead mt-6 max-w-[44rem]">
            The auditor answers one narrow question: does the page an answer cites say what the
            answer says? This page sets out each step it takes, what every mark means, and where
            it should not be trusted.
          </p>
        </div>
        <PageIndex
          items={[
            { href: "#steps", text: "The steps" },
            { href: "#marks", text: "The marks" },
            { href: "#limits", text: "Where not to trust it" },
            { href: "#live", text: "Live audits on this site" },
          ]}
        />
      </header>

      <section aria-labelledby="steps" className="mt-16 border-t border-ink pt-8">
        <h2 id="steps" className="display-2 scroll-mt-8">
          The steps
        </h2>
        <ol className="mt-10 grid gap-x-12 gap-y-10 md:grid-cols-2 xl:grid-cols-5">
          {steps.map((step, index) => (
            <li key={step.title} className="border-t border-rule pt-4">
              <p className="data text-ink-faint">Step {index + 1}</p>
              <h3 className="display-3 mt-2">{step.title}</h3>
              <p className="mt-3 leading-relaxed text-ink-soft">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="marks" className="mt-24 border-t border-ink pt-8">
        <div className="grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <div>
            <h2 id="marks" className="display-2 scroll-mt-8">
              The marks
            </h2>
            <p className="mt-4 max-w-[28rem] leading-relaxed text-ink-soft">
              Each has its own shape as well as its own colour. Only two of them count as a
              failed citation: not on the cited page, and contradicted.
            </p>
          </div>
          <dl className="sheet divide-y divide-rule">
            {LABEL_ORDER.map((label) => (
              <div key={label} className="grid gap-x-6 gap-y-1 px-5 py-4 sm:grid-cols-[15rem_1fr] md:px-8">
                <dt className={`flex items-center gap-2.5 font-medium ${LABEL_TONE[label]}`}>
                  <Mark kind={LABEL_MARK[label]} className="text-[1.2rem]" />
                  {LABEL_TEXT[label]}
                </dt>
                <dd className="leading-relaxed text-ink-soft">{LABEL_MEANING[label]}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section aria-labelledby="limits" className="mt-24 border-t border-ink pt-8">
        <div className="grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <div>
            <h2 id="limits" className="display-2 scroll-mt-8">
              Where not to trust it
            </h2>
            <AuditAccuracy className="mt-8 max-w-[28rem]" />
          </div>
          <ul className="grid gap-x-12 gap-y-8 md:grid-cols-2">
            {weak.map((item) => (
              <li key={item.title} className="border-t border-rule pt-4">
                <h3 className="font-medium text-ink">{item.title}</h3>
                <p className="mt-2 leading-relaxed text-ink-soft">{item.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="live" className="mt-24 border-t border-ink pt-8">
        <div className="grid gap-x-16 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <h2 id="live" className="display-2 scroll-mt-8">
            Live audits on this site
          </h2>
          <div className="max-w-[44rem] space-y-4 leading-relaxed text-ink-soft">
            <p>
              A live audit is real: it fetches the pages and calls the models while you watch.
              Each one stops at a spending cap of ${limits.audit_cap_usd.toFixed(2)}, set in code,
              and an address may run {limits.max_audits_per_ip} a day. The recorded audits are
              earlier real runs, saved with their timings.
            </p>
            <p>
              Every design decision, with what else was considered and what it cost, is written
              down in the{" "}
              <a href={`${REPO}/blob/rebuild/docs/DECISIONS.md`} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-4">
                decision log
              </a>
              . The measurements are on the{" "}
              <Link href="/evals" className="text-ink underline underline-offset-4">
                Evals page
              </Link>
              .
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
