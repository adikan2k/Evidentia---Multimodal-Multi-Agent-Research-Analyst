import type { Metadata } from "next";
import { AuditPicker } from "@/components/AuditPicker";

export const metadata: Metadata = {
  title: "Audit · Evidentia",
  description: "Paste an AI answer with its sources and see whether each citation backs its claim.",
};

export default function Page() {
  return <AuditPicker />;
}
