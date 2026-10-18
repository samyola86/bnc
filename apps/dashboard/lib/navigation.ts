import { BarChart3, FileCheck2, FolderOpen, LayoutDashboard, Newspaper, PenLine, Radio, Send, Settings } from "lucide-react";
export const navigation = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/news-feeds", label: "News Feeds", icon: Radio },
  { href: "/manual-writing", label: "Manual Writing", icon: PenLine },
  { href: "/publishing", label: "Publishing", icon: Send },
  { href: "/published", label: "Published", icon: FileCheck2 },
  { href: "/media-library", label: "Media Library", icon: FolderOpen },
  { href: "/sources", label: "Sources", icon: Newspaper },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings }
];
