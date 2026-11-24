import Link from "next/link";
import { REPO, SHELL } from "@/components/SiteHeader";

const AUTHOR = "https://github.com/adikan2k";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-rule">
      <div className={`${SHELL} label flex flex-wrap items-center justify-between gap-x-8 gap-y-2 py-6 text-ink-soft`}>
        <p>
          Built by{" "}
          <a href={AUTHOR} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-4">
            Aditya Kanbargi
          </a>
          . Every number on this site is read from a results file in the repository.
        </p>
        <nav aria-label="Footer" className="-mx-2 flex flex-wrap items-center">
          <Link href="/method" className="flex min-h-10 items-center px-2 hover:text-ink">
            Method and limits
          </Link>
          <Link href="/evals" className="flex min-h-10 items-center px-2 hover:text-ink">
            Evals
          </Link>
          <a href={REPO} target="_blank" rel="noreferrer" className="flex min-h-10 items-center px-2 hover:text-ink">
            Code and decisions ↗
          </a>
          <a href={`${AUTHOR}`} target="_blank" rel="noreferrer" className="flex min-h-10 items-center px-2 hover:text-ink">
            Contact ↗
          </a>
        </nav>
      </div>
    </footer>
  );
}
