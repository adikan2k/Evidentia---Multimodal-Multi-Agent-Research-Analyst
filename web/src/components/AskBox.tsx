"use client";

import { useState } from "react";

type Props = { available: boolean | null; onAsk: (question: string) => void };

/** The question box. A live run is real: it searches, reads and calls the models. */
export function AskBox({ available, onAsk }: Props) {
  const [question, setQuestion] = useState("");
  // Usable at once: while the status is unknown the server is probably waking up, and the
  // run request itself will wait for it.
  const ready = available !== false && question.trim().length >= 10;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) onAsk(question.trim());
      }}
      className="sheet p-4 md:p-5"
    >
      <label htmlFor="question" className="label text-ink">
        Your question
      </label>
      <textarea
        id="question"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        rows={3}
        maxLength={300}
        placeholder="Ask something that has an answer on the web…"
        className="sheet-text mt-2 w-full resize-y rounded-[3px] border border-rule bg-paper/40 p-3 leading-snug text-ink placeholder:text-ink-faint focus:border-ink focus:outline-none"
      />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="label font-normal text-ink-soft">
          {available !== false && "A live run takes about half a minute and draws on a small daily budget."}
          {available === false && "Live runs are paused right now. The recorded runs below are real ones."}
        </p>
        <button
          type="submit"
          disabled={!ready}
          className="label min-h-11 rounded-full bg-ink px-6 text-sheet transition-opacity hover:opacity-85 disabled:opacity-35"
        >
          Run it live
        </button>
      </div>
    </form>
  );
}
