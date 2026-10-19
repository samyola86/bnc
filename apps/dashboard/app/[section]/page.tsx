import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/layout/page-header";

const sections: Record<string, { title: string; description: string; empty: string; detail: string }> = {
  published: { title: "Published", description: "Track confirmed publications, updates, corrections, and retractions.", empty: "No confirmed publications", detail: "Each destination will retain its own remote URL, revision, and delivery history." },
  "media-library": { title: "Media Library", description: "Manage editorial media, attribution, usage rights, and alt text.", empty: "Your media library is empty", detail: "The local object storage service is provisioned. Upload and rights validation workflows are planned." },
  analytics: { title: "Analytics", description: "Understand editorial throughput and destination performance.", empty: "No measurements yet", detail: "Future reports will include metric definitions, source, and capture time. Analytics integrations are inactive." },
  settings: { title: "Settings", description: "Manage newsroom preferences, roles, and integration connections.", empty: "Connections are inactive", detail: "This foundation uses Asia/Dhaka for display and UTC for stored timestamps. Authentication, role management, and secrets-backed connections are planned." }
};
export function generateStaticParams() { return Object.keys(sections).map(section => ({ section })); }
export async function generateMetadata({ params }: { params: Promise<{ section: string }> }): Promise<Metadata> { return { title: sections[(await params).section]?.title ?? "Not found" }; }
export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const config = sections[section];
  if (!config) notFound();
  return <><PageHeader title={config.title} description={config.description} /><EmptyState title={config.empty} description={config.detail} /></>;
}
