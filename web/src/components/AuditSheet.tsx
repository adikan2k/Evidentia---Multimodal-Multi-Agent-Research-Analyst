"use client";

import { useEffect, useRef, useState } from "react";
import { Mark } from "@/components/Mark";
import {
  type AuditLabel,
  LABEL_LINE,
  LABEL_MARK,
  LABEL_SHORT,
  LABEL_TEXT,
  LABEL_TONE,
  type Sentence,
} from "@/lib/audit";

type Props = {
  text: string;
  sentences: Sentence[];
  judged: boolean;
  selected: number | null;
  onSelect: (index: number) => void;
  caption?: React.ReactNode;
  children?: React.ReactNode;
};

const GAP = 30; // least distance, in pixels, between two marks in the margin

/**
 * The audited answer, set as a document on a sheet of paper. Each sentence the splitter took
 * claims from is underlined. Its verdict is drawn in the margin as a proofreader's mark with
 * its name, level with the sentence's first line. When the sheet itself is narrow (a phone, or
 * beside the evidence panel on a small laptop) there is no margin, so the mark sits at the end of
 * the sentence. This goes by the sheet's width, not the screen's.
 */
export function AuditSheet({ text, sentences, judged, selected, onSelect, caption, children }: Props) {
  const body = useRef<HTMLDivElement>(null);
  const spans = useRef<(HTMLSpanElement | null)[]>([]);
  const [tops, setTops] = useState<number[]>([]);

  // Where each sentence's first line sits. Measured once the text is laid out, and again
  // whenever the sheet changes size. A mark never sits closer than GAP to the one above it.
  const layoutKey = `${text.length}:${sentences.map((s) => `${s.start}-${s.end}`).join(",")}`;
  useEffect(() => {
    const sheet = body.current;
    if (!sheet) return;
    const measure = () => {
      const origin = sheet.getBoundingClientRect().top;
      let previous = -GAP;
      const next = spans.current.slice(0, layoutKey.split(",").length).map((span) => {
        const first = span?.getClientRects()[0];
        const top = Math.round(Math.max((first?.top ?? origin) - origin, previous + GAP));
        previous = top;
        return top;
      });
      setTops((now) => (now.length === next.length && now.every((t, i) => t === next[i]) ? now : next));
    };
    const soon = setTimeout(measure, 0);
    const observer = new ResizeObserver(measure);
    observer.observe(sheet);
    return () => {
      clearTimeout(soon);
      observer.disconnect();
    };
  }, [layoutKey]);

  const verdict = (s: Sentence): AuditLabel | null => (judged ? s.label : null);

  const parts: React.ReactNode[] = [];
  let pos = 0;
  sentences.forEach((sentence, index) => {
    if (sentence.start > pos) parts.push(text.slice(pos, sentence.start));
    const label = verdict(sentence);
    const words = text.slice(sentence.start, sentence.end);
    parts.push(
      <span
        key={`${sentence.start}-${sentence.end}`}
        ref={(el) => {
          spans.current[index] = el;
        }}
        role="button"
        tabIndex={0}
        aria-pressed={selected === index}
        aria-label={`${words} (${label ? LABEL_TEXT[label] : "being checked"})`}
        onClick={() => onSelect(index)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(index);
          }
        }}
        className={`cursor-pointer rounded-[2px] underline decoration-[1.5px] underline-offset-[0.28em] transition-colors duration-300 ${
          label ? LABEL_LINE[label] : "decoration-ink-faint decoration-dotted"
        } ${selected === index ? "bg-paper-deep" : "hover:bg-paper"}`}
      >
        {words}
        {label && (
          <Mark kind={LABEL_MARK[label]} className={`ml-1 @xl:hidden ${LABEL_TONE[label]}`} />
        )}
      </span>,
    );
    pos = sentence.end;
  });
  if (pos < text.length) parts.push(text.slice(pos));

  return (
    <article className="sheet @container">
      <header className="label flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-5 py-3 text-ink-soft md:px-8">
        <span>{caption ?? "The answer under audit"}</span>
        <span className="text-ink-faint">Select a sentence to see its evidence</span>
      </header>
      <div ref={body} className="relative px-5 py-7 md:py-9 @xl:pr-10 @xl:pl-[11.5rem]">
        {/* The margin: one mark per sentence, level with its first line. */}
        <div className="absolute inset-y-0 left-0 hidden w-[11.5rem] border-r border-rule @xl:block" aria-hidden="true">
          {sentences.map((sentence, index) => {
            const label = verdict(sentence);
            return (
              <button
                key={`${sentence.start}-${sentence.end}`}
                type="button"
                tabIndex={-1}
                onClick={() => onSelect(index)}
                style={{ top: tops[index] ?? 0 }}
                className={`label absolute right-3 left-4 flex items-center gap-2 rounded-[3px] px-1.5 py-0.5 text-left transition-[top,background-color] duration-300 ${
                  selected === index ? "bg-paper-deep" : "hover:bg-paper"
                } ${label ? LABEL_TONE[label] : "text-ink-faint"}`}
              >
                {label ? (
                  <>
                    <Mark key={label} kind={LABEL_MARK[label]} draw className="text-[1.15rem]" />
                    <span>{LABEL_SHORT[label]}</span>
                  </>
                ) : (
                  <>
                    <Mark kind="dots" className="animate-pulse text-[1.15rem]" />
                    <span>Checking</span>
                  </>
                )}
              </button>
            );
          })}
        </div>
        {text ? (
          <div className="sheet-text whitespace-pre-line text-ink">{parts}</div>
        ) : (
          <p className="label text-ink-faint">Reading the answer…</p>
        )}
      </div>
      {children}
    </article>
  );
}
