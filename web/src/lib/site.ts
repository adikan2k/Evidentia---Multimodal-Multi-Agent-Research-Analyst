// Shared by server and client components. It must stay a plain module: a constant exported
// from a "use client" file reaches a server component as a stub, not as its value.
export const REPO = "https://github.com/adikan2k/evidentia";

/** The page's width and side padding. Every page and the header and footer use it. */
export const SHELL = "mx-auto w-full max-w-[112rem] px-[var(--gutter)]";
