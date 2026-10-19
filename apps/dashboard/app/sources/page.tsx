import type { Metadata } from "next";
import { SourcesWorkspace } from "@/features/sources/sources-workspace";
export const metadata: Metadata = { title: "Sources" };
export default function SourcesPage() { return <SourcesWorkspace />; }
