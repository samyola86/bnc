import { IntelligenceWorkspace } from "@/features/intelligence/workspace";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <IntelligenceWorkspace clusterId={id} />;
}
