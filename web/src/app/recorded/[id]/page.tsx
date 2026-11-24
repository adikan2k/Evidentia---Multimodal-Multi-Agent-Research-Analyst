import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AuditPicker } from "@/components/AuditPicker";
import { SHELL } from "@/lib/site";

// One address per recorded audit, so an audit can be linked and previewed (D-045).
type Entry = { id: string; question: string; model: string };

async function entries(): Promise<Entry[]> {
  "use cache"; // the list is a file in the build, so every page here is made ahead of time
  const file = path.join(process.cwd(), "public", "audits", "index.json");
  return JSON.parse(await readFile(file, "utf-8"));
}

export async function generateStaticParams() {
  return (await entries()).map((entry) => ({ id: entry.id }));
}

export async function generateMetadata({ params }: PageProps<"/recorded/[id]">): Promise<Metadata> {
  const { id } = await params;
  const entry = (await entries()).find((e) => e.id === id);
  if (!entry) return {};
  const description = `An audit of ${entry.model}'s answer, claim by claim, against the pages it cites.`;
  // A page's own openGraph block replaces the site's, so the picture is named again here.
  const images = ["/opengraph-image"];
  return {
    title: entry.question,
    description,
    openGraph: { title: entry.question, description, siteName: "Evidentia", type: "article", images },
    twitter: { card: "summary_large_image", title: entry.question, description, images },
  };
}

async function Recorded({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!(await entries()).some((e) => e.id === id)) notFound();
  return <AuditPicker initial={id} />;
}

export default function Page({ params }: PageProps<"/recorded/[id]">) {
  return (
    <Suspense
      fallback={<p className={`${SHELL} label pt-16 font-normal text-ink-soft`}>Loading the recorded audit…</p>}
    >
      <Recorded params={params} />
    </Suspense>
  );
}
