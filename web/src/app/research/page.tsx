import type { Metadata } from "next";
import { ReplayPicker } from "@/components/ReplayPicker";

export const metadata: Metadata = {
  title: "Research",
  description: "Ask a question. Every claim in the answer carries an exact quote, checked by code.",
};

export default function Page() {
  return <ReplayPicker />;
}
