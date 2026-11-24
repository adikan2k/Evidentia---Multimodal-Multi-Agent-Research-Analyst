// Every number on the site comes from this file, which `python -m evals report` writes from
// the JSON files in `evals/results/`. Nothing here is typed in by hand.

import data from "@/data/evals.json";

export const evals = data;

type Interval = { value: number; ci_low: number; ci_high: number };

const SYSTEMS = evals.citation_accuracy.systems;
export type SystemName = keyof typeof SYSTEMS;

export const SYSTEM_LABELS: Record<SystemName, string> = {
  baseline: "Plain RAG, Sonnet",
  pipeline: "Evidentia before tightening",
  baseline_haiku: "Plain RAG, Haiku",
  pipeline_haiku: "Evidentia, all Haiku",
  pipeline_tighten: "Evidentia (as shipped)",
};

/** Share of the claims a system shows as backed that the judge found fully backed. */
export function fullyBacked(name: SystemName): Interval & { correct: number; claims: number } {
  return SYSTEMS[name].presented_as_backed.citation_accuracy;
}

export function system(name: SystemName) {
  const s = SYSTEMS[name];
  return {
    shownPerQuestion: s.presented_as_backed.claims_per_question.mean,
    allPerQuestion: s.all_claims.claims_per_question.mean,
    evidenceChars: s.evidence_chars_median,
    costPerQuestion: s.cost_per_question_usd,
  };
}

export const product = "pipeline_tighten" satisfies SystemName;
export const checkerModel = evals.checker_agreement.product_checker as "claude-sonnet-5-5";

/** Deliberately broken claims the product's checker refused to pass. */
export const caught = evals.checker_agreement.error_detection_on_built_pairs[checkerModel].all_built;

export function nastyTotals() {
  const cases = Object.values(evals.nasty.cases);
  return {
    passed: cases.reduce((sum, c) => sum + c.passed, 0),
    trials: cases.reduce((sum, c) => sum + c.trials, 0),
  };
}
