import Link from "next/link";

const REPO = "https://github.com/adikan2k/Evidentia---Multimodal-Multi-Agent-Research-Analyst";

export function SiteHeader() {
  return (
    <header className="mb-14 flex flex-wrap items-center justify-between gap-4">
      <Link href="/" className="font-serif text-2xl italic tracking-tight">
        Evidentia
      </Link>
      <nav className="label flex items-center gap-6 text-ink-soft">
        <Link href="/" className="underline-offset-4 hover:text-ink hover:underline">
          Run
        </Link>
        <Link href="/evals" className="underline-offset-4 hover:text-ink hover:underline">
          Evals
        </Link>
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          className="underline-offset-4 hover:text-ink hover:underline"
        >
          Code ↗
        </a>
      </nav>
    </header>
  );
}
