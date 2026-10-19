import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { ManualWorkspace } from "@/features/stories/manual-workspace";

export const metadata: Metadata = { title: "Manual Writing" };
export default function ManualPage() {
  return <><PageHeader title="Manual Writing" description="Independently authored Bengali and English stories, saved in the newsroom." /><ManualWorkspace /></>;
}
