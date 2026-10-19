import type { Metadata } from "next";
import { FeedsWorkspace } from "@/features/feeds/feeds-workspace";
export const metadata: Metadata = { title: "News Feeds" };
export default function NewsFeedsPage() { return <FeedsWorkspace />; }
