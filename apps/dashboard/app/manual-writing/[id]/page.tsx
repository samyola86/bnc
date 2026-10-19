import type { Metadata } from "next";
import { StoryEditor } from "@/features/stories/story-editor";

export const metadata: Metadata = { title: "Manual story" };
export default async function ManualStoryPage({ params }: { params: Promise<{ id: string }> }) {
  return <StoryEditor id={(await params).id} manual />;
}
