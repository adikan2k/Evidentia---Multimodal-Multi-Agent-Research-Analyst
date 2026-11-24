// The shape of a recorded run (written by `python -m evidentia.record`) and the one function
// that answers: "what should the page show at second t of this run?"

export type Label = "supported" | "partial" | "unverified";

export type Claim = {
  text: string;
  quote: string;
  source_id: string;
  url: string;
  host: string;
  title: string;
  quote_found: boolean | null;
  verdict: "supported" | "partial" | "unsupported" | null;
  label: Label | null;
  reason: string;
  revised: boolean;
  context: { before: string; after: string } | null;
  // Absent in runs recorded before PDFs were supported.
  kind?: "html" | "pdf";
  pages?: [number, number] | null;
};

export type Source = {
  id: string;
  url: string;
  host: string;
  title: string;
  kind?: "html" | "pdf";
  pages_read?: number | null;
  pages_total?: number | null;
};

/** "p. 7" or "pp. 4-5" for a quote from a PDF; null for a web page. */
export function pageLabel(claim: Pick<Claim, "pages">): string | null {
  if (!claim.pages) return null;
  const [first, last] = claim.pages;
  return first === last ? `p. ${first}` : `pp. ${first}–${last}`;
}

/** Where "open the source" goes: a PDF opens at the quote's page in the browser's viewer. */
export function sourceHref(claim: Pick<Claim, "url" | "pages">): string {
  return claim.pages ? `${claim.url}#page=${claim.pages[0]}` : claim.url;
}

export type RunEvent = {
  t: number;
  node: string;
  summary: string;
  cost_usd: number;
  data: {
    queries?: string[];
    hosts?: string[];
    sources?: Source[];
    skipped?: { host: string; reason: string }[];
    repair_queries?: string[];
    claims?: Claim[];
  };
};

export type Replay = {
  id: string;
  question: string;
  recorded_at: string;
  duration_s: number;
  models: { writer: string; checker: string };
  events: RunEvent[];
  report: {
    claims: Claim[];
    labels: Record<Label, number>;
    sources_read: number;
    sources_skipped: number;
    passages_indexed: number;
    cost: { total_usd: number; cap_usd: number };
  };
};

export type Step = { key: string; label: string; start: number; end: number; summary: string };

const STEP_LABELS: Record<string, string> = {
  plan: "Plan",
  search: "Search",
  fetch: "Read",
  index: "Index",
  retrieve: "Retrieve",
  write: "Write",
  quote_check: "Quote check",
  check: "Check",
  rewrite: "New queries",
  reretrieve: "Search again",
  revise: "Rewrite",
};

/** One step per pipeline node that actually did something, with when it started and ended. */
export function stepsOf(events: RunEvent[]): Step[] {
  const steps: Step[] = [];
  let previous = 0;
  events.forEach((event, index) => {
    const searchedAgain = (event.data.repair_queries ?? []).length > 0;
    const idle =
      (event.node === "rewrite" && !searchedAgain) ||
      (event.node === "reretrieve" && event.t - previous < 0.05);
    if (!idle) {
      steps.push({
        key: `${event.node}-${index}`,
        label: STEP_LABELS[event.node] ?? event.node,
        start: previous,
        end: event.t,
        summary: summaryOf(event),
      });
    }
    previous = event.t;
  });
  return steps;
}

function summaryOf(event: RunEvent): string {
  if (event.node === "revise") {
    const rewritten = (event.data.claims ?? []).filter((c) => c.revised && !c.label).length;
    return `rewrote ${rewritten} ${rewritten === 1 ? "claim" : "claims"} to say only what the quote says`;
  }
  return event.summary;
}

export type View = {
  claims: Claim[];
  /** Each claim's wording when the writer first produced it, to show what a rewrite changed. */
  firstDraft: string[];
  queries: string[];
  sources: NonNullable<RunEvent["data"]["sources"]>;
  skipped: NonNullable<RunEvent["data"]["skipped"]>;
  cost: number;
  finished: boolean;
};

/** Everything known at second `t`: only events that had already happened by then count. */
export function viewAt(events: RunEvent[], t: number): View {
  const view: View = {
    claims: [],
    firstDraft: [],
    queries: [],
    sources: [],
    skipped: [],
    cost: 0,
    finished: false,
  };
  for (const event of events) {
    if (event.t > t) break;
    view.cost = event.cost_usd;
    if (event.data.queries) view.queries = event.data.queries;
    if (event.data.sources) view.sources = event.data.sources;
    if (event.data.skipped) view.skipped = event.data.skipped;
    if (event.data.claims) {
      if (view.firstDraft.length === 0) view.firstDraft = event.data.claims.map((c) => c.text);
      view.claims = event.data.claims;
    }
  }
  const last = events[events.length - 1];
  view.finished = last !== undefined && t >= last.t;
  return view;
}

/** The steps every run goes through, in order. A repair round adds more after these. */
export const MAIN_STEPS = ["plan", "search", "fetch", "index", "retrieve", "write", "quote_check", "check"];

export function labelOf(node: string): string {
  return STEP_LABELS[node] ?? node;
}

export function endOf(events: RunEvent[]): number {
  const last = events[events.length - 1];
  return (last?.t ?? 0) + 1.5;
}
