"use client";

import { useState } from "react";
import { Stamp } from "@/components/ClaimList";
import { checkClaim, type Verdict } from "@/lib/api";

/**
 * Try to break it. The visitor rewrites the claim, and the real checker judges the new wording
 * against the same quote. It is shown the two strings and nothing else, exactly as in a run.
 */
export function BreakIt({ claimText, quote }: { claimText: string; quote: string }) {
  const [text, setText] = useState(claimText);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Verdict | string | null>(null);
  const changed = text.trim() !== claimText.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    setResult(await checkClaim(text.trim(), quote));
    setBusy(false);
  }

  return (
    <form onSubmit={submit} className="mt-6 border-t border-rule pt-5">
      <label htmlFor="break-it" className="label text-ink">
        Try to break it
      </label>
      <p className="label mt-1 font-normal text-ink-soft">
        Change the claim: a number, a name, a direction. The checker will judge your version
        against this quote.
      </p>
      <textarea
        id="break-it"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={600}
        className="sheet-text mt-3 w-full resize-y rounded-[3px] border border-rule bg-paper/40 p-3 text-[1.0625rem] leading-snug text-ink focus:border-ink focus:outline-none"
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy || text.trim().length < 3}
          className="label min-h-10 rounded-full bg-ink px-4 text-sheet transition-opacity hover:opacity-85 disabled:opacity-40"
        >
          {busy ? "Checking…" : changed ? "Check my version" : "Check it as written"}
        </button>
        {changed && (
          <button
            type="button"
            onClick={() => {
              setText(claimText);
              setResult(null);
            }}
            className="label min-h-10 px-2 text-ink-soft underline underline-offset-4 hover:text-ink"
          >
            Reset
          </button>
        )}
      </div>
      {typeof result === "string" && <p className="label mt-4 font-normal text-unverified">{result}</p>}
      {result && typeof result !== "string" && (
        <div className="mt-4">
          <Stamp label={result.label} />
          <p className="label mt-2 font-normal text-ink-soft">{result.reason}</p>
        </div>
      )}
    </form>
  );
}
