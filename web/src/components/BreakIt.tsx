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
      <p className="label text-ink-soft">Try to break it</p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
        Change the claim: a number, a name, a direction. The checker will judge your version
        against this quote.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={600}
        aria-label="Your version of the claim"
        className="mt-3 w-full resize-y rounded-md border border-rule bg-paper p-3 font-serif text-lg leading-snug outline-none transition-colors focus:border-ink"
      />
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={busy || text.trim().length < 3}
          className="label rounded-full bg-ink px-4 py-2 text-paper transition-opacity hover:opacity-85 disabled:opacity-40"
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
            className="label text-ink-soft underline-offset-4 hover:text-ink hover:underline"
          >
            Reset
          </button>
        )}
      </div>
      {typeof result === "string" && <p className="mt-4 text-sm text-unverified">{result}</p>}
      {result && typeof result !== "string" && (
        <div className="mt-4">
          <Stamp label={result.label} />
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">{result.reason}</p>
        </div>
      )}
    </form>
  );
}
