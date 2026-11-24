"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const REPO = "https://github.com/adikan2k/Evidentia---Multimodal-Multi-Agent-Research-Analyst";
/** The page frame: as wide as the screen, up to 112rem, with padding that grows with it. */
export const SHELL = "mx-auto w-full max-w-[112rem] px-[var(--gutter)]";

const LINKS = [
  { href: "/", label: "Audit" },
  { href: "/research", label: "Research" },
  { href: "/evals", label: "Evals" },
  { href: "/method", label: "Method" },
];

export function SiteHeader() {
  const path = usePathname();
  const here = (href: string) => (href === "/" ? path === "/" || path.startsWith("/recorded") : path.startsWith(href));

  return (
    <header className="border-b border-rule">
      <div className={`${SHELL} flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2`}>
        <Link href="/" className="flex min-h-10 items-center text-xl font-semibold tracking-tight">
          Evidentia
        </Link>
        <nav aria-label="Main" className="label -mx-2 flex flex-wrap items-center">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={here(link.href) ? "page" : undefined}
              className={`flex min-h-10 items-center px-3 transition-colors hover:text-ink ${
                here(link.href) ? "text-ink underline decoration-2 underline-offset-8" : "text-ink-soft"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="flex min-h-10 items-center px-3 text-ink-soft transition-colors hover:text-ink"
          >
            Code ↗
          </a>
        </nav>
      </div>
    </header>
  );
}
