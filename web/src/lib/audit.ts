// The shape of an audit (written by `python -m evidentia.audit.record`, or streamed by the API's
// `/audits`) and the functions that answer: "what should the page show at second t?"

import type { StripItem } from "@/components/PipelineStrip";
import type { Step } from "@/lib/replay";

export type AuditLabel =
  | "supported"
  | "partial"
  | "contradicted"
  | "needs_human"
  | "not_found"
  | "dead_link"
  | "unchecked"
  | "citation_unread"
  | "uncited";

export const LABEL_TEXT: Record<AuditLabel, string> = {
  supported: "Supported",
  partial: "Partly backed",
  contradicted: "Contradicted",
  needs_human: "Needs a human",
  not_found: "Not on the cited page",
  dead_link: "Dead link",
  unchecked: "Could not check",
  citation_unread: "Could not read the citation",
  uncited: "Uncited",
};

/** Text colour for each label, from the theme in globals.css. */
export const LABEL_TONE: Record<AuditLabel, string> = {
  supported: "text-supported",
  partial: "text-partial",
  contradicted: "text-contradicted",
  needs_human: "text-human",
  not_found: "text-unverified",
  dead_link: "text-unverified",
  unchecked: "text-ink-faint",
  citation_unread: "text-ink-faint",
  uncited: "text-ink-faint",
};

/** The underline under a sentence in the answer, in its label's colour. */
export const LABEL_LINE: Record<AuditLabel, string> = {
  supported: "decoration-supported",
  partial: "decoration-partial",
  contradicted: "decoration-contradicted",
  needs_human: "decoration-human",
  not_found: "decoration-unverified",
  dead_link: "decoration-unverified",
  unchecked: "decoration-ink-faint",
  citation_unread: "decoration-ink-faint",
  uncited: "decoration-rule",
};

/** When one sentence holds several claims, it shows the most serious label among them. */
const SEVERITY: AuditLabel[] = [
  "contradicted",
  "not_found",
  "dead_link",
  "needs_human",
  "partial",
  "unchecked",
  "citation_unread",
  "supported",
  "uncited",
];

export type AuditQuote = {
  text: string;
  pages: [number, number] | null;
  context: { before: string; after: string } | null;
};

export type AuditPage = {
  citation_id: string;
  url: string;
  host: string;
  title: string;
  kind: "html" | "pdf";
  label: AuditLabel;
  quote_label: AuditLabel;
  skipped: string | null;
  quotes: AuditQuote[];
  quote_reason: string;
  page_judged: string | null;
  page_reason: string;
};

export type AuditClaim = {
  sentence: string;
  start: number;
  end: number;
  claim: string;
  citation_ids: string[];
  cited_by: "sentence" | "paragraph" | null;
  /** Markers on the sentence, such as "7" for [7], that match no source in the answer. */
  unread_markers?: string[];
  // Only once both judges have ruled:
  label?: AuditLabel;
  disputed?: boolean;
  pages?: AuditPage[];
};

export type Scorecard = {
  claims: number;
  labels: Record<AuditLabel, number>;
  cited_claims: number;
  claims_with_a_verdict: number;
  failed_citations: number;
  failed_share_of_verdicts: number | null;
  partly_backed: number;
  pages_cited: number;
  pages_read: number;
  dead_links: number;
  usd: number;
};

export type AuditEvent = {
  t: number;
  node: string;
  summary: string;
  cost_usd: number;
  data: {
    answer_text?: string;
    citations?: { id: string; url: string; host: string }[];
    claims?: AuditClaim[];
    not_located?: number;
    read?: { url: string; host: string; title: string; kind: string }[];
    skipped?: { url: string; host: string; reason: string }[];
  };
};

export type AuditReport = {
  answer_text: string;
  claims: AuditClaim[];
  scorecard: Scorecard;
  cost: { total_usd: number; cap_usd: number };
};

export type RecordedAudit = {
  id: string;
  question: string;
  answer: { model: string; tool: string; made_at: string; text: string; usd: number };
  recorded_at: string;
  duration_s: number;
  judges: { quote: string; finder: string; page: string };
  events: AuditEvent[];
  report: AuditReport;
};

const STEP_LABELS: Record<string, string> = {
  parse: "Citations",
  split: "Claims",
  fetch: "Read pages",
  find: "Find quotes",
  page_check: "Page judge",
  quote_check: "Quote check",
  check: "Quote judge",
  combine: "Combine",
};
export const AUDIT_STEPS = Object.keys(STEP_LABELS);

/** One step per audit node, with when it started and ended. */
export function auditSteps(events: AuditEvent[]): Step[] {
  let previous = 0;
  return events.map((event, index) => {
    const step = {
      key: `${event.node}-${index}`,
      label: STEP_LABELS[event.node] ?? event.node,
      start: previous,
      end: event.t,
      summary: event.summary,
    };
    previous = event.t;
    return step;
  });
}

/** A live audit: the steps finished so far, then the ones still to come. */
export function liveAuditItems(events: AuditEvent[], finished: boolean): StripItem[] {
  const done = new Set(events.map((e) => e.node));
  const items: StripItem[] = auditSteps(events).map((s) => ({
    key: s.key,
    label: s.label,
    progress: 1,
    state: "done",
    summary: s.summary,
  }));
  if (finished) return items;
  const left = AUDIT_STEPS.filter((node) => !done.has(node));
  return [
    ...items,
    ...left.map((node, i): StripItem => ({
      key: node,
      label: STEP_LABELS[node],
      progress: i === 0 ? 0.5 : 0,
      state: i === 0 ? "running" : "pending",
      summary: "",
    })),
  ];
}

export type AuditView = {
  answerText: string;
  claims: AuditClaim[];
  judged: boolean;
  read: number;
  notRead: { host: string; reason: string }[];
  cost: number;
  finished: boolean;
};

/** Everything known at second `t`: only events that had already happened by then count. */
export function auditViewAt(events: AuditEvent[], t: number): AuditView {
  const view: AuditView = {
    answerText: "",
    claims: [],
    judged: false,
    read: 0,
    notRead: [],
    cost: 0,
    finished: false,
  };
  for (const event of events) {
    if (event.t > t) break;
    view.cost = event.cost_usd;
    if (event.data.answer_text !== undefined) view.answerText = event.data.answer_text;
    if (event.data.read) view.read = event.data.read.length;
    if (event.data.skipped) view.notRead = event.data.skipped;
    if (event.data.claims) {
      view.claims = event.data.claims;
      view.judged = event.node === "combine";
    }
  }
  const last = events[events.length - 1];
  view.finished = last !== undefined && t >= last.t;
  return view;
}

export type Sentence = { start: number; end: number; claims: AuditClaim[]; label: AuditLabel | null };

/** The answer's claims grouped by the sentence they come from, in reading order. */
export function sentencesOf(claims: AuditClaim[]): Sentence[] {
  const byPlace = new Map<string, Sentence>();
  for (const claim of claims) {
    const key = `${claim.start}-${claim.end}`;
    const sentence = byPlace.get(key) ?? { start: claim.start, end: claim.end, claims: [], label: null };
    sentence.claims.push(claim);
    byPlace.set(key, sentence);
  }
  const sorted = [...byPlace.values()].sort((a, b) => a.start - b.start);
  const kept: Sentence[] = [];
  for (const sentence of sorted) {
    if (kept.length && sentence.start < kept[kept.length - 1].end) continue; // overlaps: skip
    const labels = sentence.claims.map((c) => c.label).filter((l): l is AuditLabel => !!l);
    sentence.label = SEVERITY.find((l) => labels.includes(l)) ?? null;
    kept.push(sentence);
  }
  return kept;
}

/** "p. 7" or "pp. 4–5" for a quote from a PDF; null for a web page. */
export function quotePages(quote: AuditQuote): string | null {
  if (!quote.pages) return null;
  const [first, last] = quote.pages;
  return first === last ? `p. ${first}` : `pp. ${first}–${last}`;
}
