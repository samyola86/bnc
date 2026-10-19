import type { Metadata } from "next";
import { CandidateDraftEditor } from "@/features/feeds/candidate-draft-editor";
export const metadata: Metadata = { title: "Candidate draft" };
export default async function DraftPage({ params }: { params: Promise<{ id: string }> }) {
  return <CandidateDraftEditor id={(await params).id} />;
}
