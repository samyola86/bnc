import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { StoryEditor } from "@/features/stories/story-editor";

const sections: Record<string, { title: string; description: string; empty: string; detail: string }> = {
  "news-feeds": { title: "News Feeds", description: "Discover, rank, and select incoming stories with source provenance.", empty: "No incoming stories yet", detail: "Feed ingestion is planned. Future editorial cycles will surface 20–50 candidates for selection." },
  "manual-writing": { title: "Manual Writing", description: "A full-page workspace for Bengali and English stories.", empty: "", detail: "" },
  publishing: { title: "Publishing", description: "Prepare approved revisions for independent channel delivery.", empty: "Your publishing queue is empty", detail: "Scheduling, approvals, channel previews, and retries will appear here when the editorial workflow is implemented." },
  published: { title: "Published", description: "Track confirmed publications, updates, corrections, and retractions.", empty: "No confirmed publications", detail: "Each destination will retain its own remote URL, revision, and delivery history." },
  "media-library": { title: "Media Library", description: "Manage editorial media, attribution, usage rights, and alt text.", empty: "Your media library is empty", detail: "The local object storage service is provisioned. Upload and rights validation workflows are planned." },
  sources: { title: "Sources", description: "Maintain publishers, feed health, polling intervals, and permitted usage.", empty: "No sources registered", detail: "The source registry schema is ready. Source management and RSS fetching are planned." },
  analytics: { title: "Analytics", description: "Understand editorial throughput and destination performance.", empty: "No measurements yet", detail: "Future reports will include metric definitions, source, and capture time. Analytics integrations are inactive." },
  settings: { title: "Settings", description: "Manage newsroom preferences, roles, and integration connections.", empty: "Connections are inactive", detail: "This foundation uses Asia/Dhaka for display and UTC for stored timestamps. Authentication, role management, and secrets-backed connections are planned." }
};
export function generateStaticParams() { return Object.keys(sections).map(section => ({ section })); }
export async function generateMetadata({ params }: { params: Promise<{ section: string }> }): Promise<Metadata> { return { title: sections[(await params).section]?.title ?? "Not found" }; }
export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const config = sections[section];
  if (!config) notFound();
  return <><PageHeader title={config.title} description={config.description} />{section === "manual-writing" ? <StoryEditor /> : <EmptyState title={config.empty} description={config.detail} />}</>;
}
