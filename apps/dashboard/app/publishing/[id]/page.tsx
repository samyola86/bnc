import { ReviewWorkspace } from "@/features/stories/publishing-workspace";
export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  return <ReviewWorkspace id={(await params).id} />;
}
