// The real-world audit (D-042 to D-048), for the findings page. Every number comes from the site's
// data file, which `python -m evals report` writes from `evals/results/`. Nothing is typed in.

import type { AuditLabel } from "@/lib/audit";
import { evals } from "@/lib/evals";

export type Tool = "openai" | "claude";
export const TOOLS: Tool[] = ["openai", "claude"];

// The tools as they were asked (evidentia/audit/answers.py). Names, not numbers.
export const TOOL_NAME: Record<Tool, string> = { openai: "OpenAI", claude: "Claude" };
export const TOOL_MODEL: Record<Tool, string> = {
  openai: "gpt-6.2-sol with web search",
  claude: "Claude Sonnet 5.5 with web search",
};

export type Interval = { value: number | null; ci_low: number | null; ci_high: number | null };

const data = evals as unknown as Record<string, unknown>;

type Measures = {
  questions: number;
  claims: number;
  headline_failed_share: Interval;
  headline_claims: number;
  verified_share_of_all_claims: Interval;
  labels: Record<AuditLabel, { claims: number; share: number | null }>;
  headline_bounds: { unread_pages: { if_all_supported: number; if_none_supported: number } };
  usd_per_answer: number;
  usd_per_audit: number;
};

type Judge = {
  page_judge: string;
  tools: Record<Tool, Measures>;
  openai_minus_claude: Interval;
  openai_minus_claude_verified_share_of_all_claims: Interval;
};

type RealWorld = { generated_at: string; questions: number; judges: Record<"haiku" | "luna", Judge> };

type Reask = {
  questions: string[];
  repeats: number;
  search_cap: number;
  tools: Record<
    Tool,
    {
      headline_across_repeats: { min: number; max: number };
      searches: { answers: number; max: number; answers_with_no_search: number };
      runs: Record<string, { headline_failed_share: Interval }>;
      usd: { answers: number; audits: number };
    }
  >;
  openai_minus_claude: Record<string, Interval>;
  openai_markers: { annotations: number; links_the_tool_wrote_inline: number };
};

type Reread = {
  runs: Record<
    "main" | "reask",
    { pages: { tried: number; read: number }; tools: Record<Tool, { usd: number }> }
  >;
};

type Short = {
  runs: Record<
    "main" | "reask",
    {
      tools: Record<Tool, { usd: number; with_short_pages: { headline_failed_share: Interval } }>;
      openai_minus_claude: Record<string, Interval>;
    }
  >;
};

type Share = {
  hits: number;
  n: number;
  share: number | null;
  ci_low: number | null;
  ci_high: number | null;
  unsure: number;
  would_not_open: number;
};

export type HandCheck = {
  items_in_sample: number;
  items_checked: number;
  median_seconds_per_item: number | null;
  flags_upheld: Record<"both_tools" | Tool, Share>;
  supported_upheld: Record<"both_tools" | Tool, Share>;
  rule: {
    flags_upheld_needed_both_tools: number;
    per_tool_guard?: { tools_clearly_below: Tool[] };
    met: boolean;
  };
};

// The audits as first run (D-042). The comparison page reads these. If a later hand check ever
// meets the rule, that page must first be moved to the D-049 re-audit below (see D-049's result).
export const realworld = data.realworld as RealWorld;
export const reask = data.realworld_reask as Reask;
/** The same saved answers audited again with the fixed page reader (D-049). */
const restOfPage = data.realworld_rest_of_page as RealWorld | undefined;
const restOfPageReask = data.realworld_rest_of_page_reask as Reask | undefined;
export const reread = data.realworld_rendered as Reread;
export const short = data.realworld_short as Short;
/** The first check, on the audits as first run (D-044). The example pages come from these. */
export const firstHandCheck = data.realworld_hand_check as HandCheck | undefined;
/** The second check, on the audits after the page reader was fixed (D-049). */
export const secondHandCheck = data.realworld_hand_check_2 as HandCheck | undefined;
/** The check that governs the page: the latest one, on the auditor as it is now. */
export const handCheck = secondHandCheck ?? firstHandCheck;
/** D-044: when the hand check misses its rule, the site makes no comparison between the tools. */
export const withheld = handCheck !== undefined && !handCheck.rule.met;

export const shipped = realworld.judges.haiku;
export const otherJudge = realworld.judges.luna;

/**
 * "38.0%" from 0.3797. Rounds half up on the stored four decimals, so 0.0785 reads 7.9%, as it
 * does in the docs, and not 7.8% as binary floating point would make it.
 */
export function pct(value: number | null, digits = 1): string {
  if (value === null) return "n/a";
  const scale = 10 ** digits;
  return `${(Math.round(value * 100 * scale + 1e-6) / scale).toFixed(digits)}%`;
}

/**
 * "30 points (21 to 38)" from a difference of shares with its interval. A negative difference is
 * turned round, so the size is always positive and the interval is read in the same direction.
 */
export function points(d: Interval): string {
  if (d.value === null) return "n/a";
  const sign = d.value < 0 ? -1 : 1;
  const p = (v: number) => {
    const n = Math.round(v * 100 * sign);
    return n < 0 ? `−${-n}` : `${n}`;
  };
  if (d.ci_low === null || d.ci_high === null) return `${p(d.value)} points`;
  const [lo, hi] = sign > 0 ? [d.ci_low, d.ci_high] : [d.ci_high, d.ci_low];
  return `${p(d.value)} points (${p(lo)} to ${p(hi)})`;
}

/** Which tool a difference (OpenAI minus Claude) favours on the measure. */
export function higher(d: Interval): Tool {
  return (d.value ?? 0) < 0 ? "claude" : "openai";
}

/** True when the interval lies wholly on one side of zero. */
export function clearOfZero(d: Interval): boolean {
  return d.ci_low !== null && d.ci_high !== null && (d.ci_low > 0 || d.ci_high < 0);
}

export function range(i: Interval): string {
  return i.ci_low === null || i.ci_high === null ? "" : `${pct(i.ci_low)} to ${pct(i.ci_high)}`;
}

/** The whole study's model and search spend, added up from the result files. */
export function studyCost(): number {
  const audits = (run: RealWorld, tool: Tool) =>
    Object.values(run.judges).reduce(
      (s, judge) => s + judge.tools[tool].usd_per_audit * judge.tools[tool].questions,
      0,
    );
  const main = TOOLS.reduce(
    (sum, tool) =>
      sum +
      shipped.tools[tool].usd_per_answer * shipped.tools[tool].questions +
      audits(realworld, tool) +
      (restOfPage ? audits(restOfPage, tool) : 0),
    0,
  );
  const again = TOOLS.reduce(
    (sum, t) =>
      sum + reask.tools[t].usd.answers + reask.tools[t].usd.audits + (restOfPageReask?.tools[t].usd.audits ?? 0),
    0,
  );
  const pages = (["main", "reask"] as const).reduce(
    (sum, run) =>
      sum + TOOLS.reduce((s, t) => s + reread.runs[run].tools[t].usd + short.runs[run].tools[t].usd, 0),
    0,
  );
  return main + again + pages;
}

// The examples (web/public/findings/index.json), written by `python -m evals realworld examples`.
export type Example = {
  id: string;
  tool: Tool;
  question: string;
  question_text: string;
  claim_index: number;
  label: AuditLabel;
  claim: string;
  cited_by: "sentence" | "paragraph" | null;
  why: string;
};

export type ExampleIndex = { rule: string; seed: number; examples: Example[] };

/** The lowest and highest failure rate a tool had over the first ask and every repeat. */
export function askedAgainRange(tool: Tool): { min: number; max: number; asks: number } {
  const values = Object.values(reask.tools[tool].runs)
    .map((r) => r.headline_failed_share.value)
    .filter((v): v is number => v !== null);
  return { min: Math.min(...values), max: Math.max(...values), asks: values.length };
}

