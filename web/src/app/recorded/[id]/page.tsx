import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AuditPicker } from "@/components/AuditPicker";

// One address per recorded audit, so an audit can be linked and previewed (D-045).
type Entry = { id: string; question: string; model: string };

async function entries(): Promise<Entry[]> {
  const file = path.join(process.cwd(), "public", "audits", "index.json");
  return JSON.parse(await readFile(file, "utf-8"));
}

export async function generateStaticParams() {
  return (await entries()).map((entry) => ({ id: entry.id }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: PageProps<"/recorded/[id]">): Promise<Metadata> {
  const { id } = await params;
  const entry = (await entries()).find((e) => e.id === id);
  if (!entry) return {};
  const description = `An audit of ${entry.model}'s answer, claim by claim, against the pages it cites.`;
  return {
    title: entry.question,
    description,
    openGraph: { title: entry.question, description },
  };
}

export default async function Page({ params }: PageProps<"/recorded/[id]">) {
  const { id } = await params;
  if (!(await entries()).some((e) => e.id === id)) notFound();
  return <AuditPicker initial={id} />;
}
