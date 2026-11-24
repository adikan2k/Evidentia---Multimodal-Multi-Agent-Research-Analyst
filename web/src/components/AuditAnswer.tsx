"use client";

import { type AuditLabel, LABEL_LINE, LABEL_TEXT, type Sentence } from "@/lib/audit";

type Props = {
  text: string;
  sentences: Sentence[];
  judged: boolean;
  selected: number | null;
  onSelect: (index: number) => void;
};

/**
 * The audited answer as text. Each sentence the splitter took claims from is underlined: a
 * dashed grey line while the judges are still working, then a line in its label's colour once
 * both judges have ruled. Clicking a sentence opens its evidence.
 */
export function AuditAnswer({ text, sentences, judged, selected, onSelect }: Props) {
  if (!text) {
    return <p className="label text-ink-faint">Reading the answer…</p>;
  }
  const parts: React.ReactNode[] = [];
  let pos = 0;
  sentences.forEach((sentence, index) => {
    if (sentence.start > pos) parts.push(text.slice(pos, sentence.start));
    const label: AuditLabel | null = judged ? sentence.label : null;
    const tone = label ? LABEL_LINE[label] : "decoration-ink-faint decoration-dashed";
    parts.push(
      <button
        key={`${sentence.start}-${sentence.end}`}
        type="button"
        onClick={() => onSelect(index)}
        aria-label={`${text.slice(sentence.start, sentence.end)} (${label ? LABEL_TEXT[label] : "being checked"})`}
        title={label ? LABEL_TEXT[label] : "Being checked"}
        className={`cursor-pointer rounded-sm text-left underline decoration-2 underline-offset-[5px] transition-[background-color,text-decoration-color] duration-500 ${tone} ${
          selected === index ? "bg-marker/60" : "hover:bg-paper-deep"
        }`}
      >
        {text.slice(sentence.start, sentence.end)}
      </button>,
    );
    pos = sentence.end;
  });
  if (pos < text.length) parts.push(text.slice(pos));

  return (
    <div className="whitespace-pre-line font-serif text-[1.3rem] leading-[1.75] text-ink">{parts}</div>
  );
}
