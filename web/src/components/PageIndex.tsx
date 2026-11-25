/** The contents of a long page, as numbered links to its sections. Sits beside the headline. */
export function PageIndex({ items }: { items: { href: string; text: string }[] }) {
  return (
    <nav aria-label="On this page" className="border-t border-ink">
      <ol>
        {items.map((item, index) => (
          <li key={item.href} className="border-b border-rule">
            <a
              href={item.href}
              className="group flex min-h-12 items-center gap-4 py-2 text-ink-soft transition-colors hover:text-ink"
            >
              <span className="data text-ink-faint">{String(index + 1).padStart(2, "0")}</span>
              <span className="flex-1 font-medium">{item.text}</span>
              <span aria-hidden="true" className="transition-transform duration-200 group-hover:translate-y-0.5">
                ↓
              </span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
