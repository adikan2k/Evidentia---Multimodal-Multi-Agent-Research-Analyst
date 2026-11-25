// Reads the examples written by `python -m evals realworld examples`. Server only: the files are
// part of the build, so every findings page is made ahead of time.

import { readFile } from "node:fs/promises";
import path from "node:path";
import type { AuditReport } from "@/lib/audit";
import type { ExampleIndex, Tool } from "@/lib/findings";

const DIR = path.join(process.cwd(), "public", "findings");

export type ExampleAnswer = {
  tool: Tool;
  question_id: string;
  question: string;
  source: string;
  answer: { model: string | null; made_at: string | null; usd: number | null };
  report: AuditReport;
};

export async function exampleIndex(): Promise<ExampleIndex> {
  "use cache";
  return JSON.parse(await readFile(path.join(DIR, "index.json"), "utf-8"));
}

export async function exampleAnswer(tool: Tool, question: string): Promise<ExampleAnswer> {
  "use cache";
  return JSON.parse(await readFile(path.join(DIR, "answers", `${tool}-${question}.json`), "utf-8"));
}
