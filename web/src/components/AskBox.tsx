"use client";

import { useState } from "react";

type Props = { available: boolean | null; onAsk: (question: string) => void };

/** The question box. A live run is real: it searches, reads and calls the models. */
export function AskBox({ available, onAsk }: Props) {
  const [question, setQuestion] = useState("");
  const ready = available === true && question.trim().length >= 10;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) onAsk(question.trim());
      }}
      className="mb-14"
    >
      <div className="flex flex-wrap items-end gap-3 border-b border-ink pb-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder="Ask a question that has an answer on the web"
          aria-label="Your question"
          className="min-w-0 flex-1 bg-transparent font-serif text-2xl leading-tight outline-none placeholder:text-ink-faint"
        />
        <button
          type="submit"
          disabled={!ready}
          className="label rounded-full bg-ink px-4 py-2 text-paper transition-opacity hover:opacity-85 disabled:opacity-30"
        >
          Run it live
        </button>
      </div>
      <p className="label mt-2.5 text-ink-faint normal-case tracking-normal">
        {available === null && "Checking whether live runs are available…"}
        {available === true &&
          "A live run takes about half a minute and draws on a small daily budget."}
        {available === false &&
          "Live runs are not available right now. The recorded runs below are real ones."}
      </p>
    </form>
  );
}
