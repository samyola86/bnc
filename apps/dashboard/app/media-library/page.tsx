import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { MediaLibrary } from "@/features/media/media-library";

export const metadata: Metadata = { title: "Media Library" };
export default function MediaLibraryPage() {
  return <><PageHeader title="Media Library" description="Upload, browse and reuse newsroom images." /><MediaLibrary /></>;
}
