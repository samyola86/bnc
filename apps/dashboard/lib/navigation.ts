import { BarChart3, FileCheck2, FolderOpen, LayoutDashboard, Newspaper, PenLine, Radio, Send, Settings } from "lucide-react";
export const navigation = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/news-feeds", label: "News Feeds", icon: Radio },
  { href: "/trending", label: "Trending Stories", icon: BarChart3 },
  { href: "/recommendations", label: "Recommended for Publishing", icon: Newspaper },
  { href: "/manual-writing", label: "Manual Writing", icon: PenLine },
  { href: "/publishing", label: "Publishing", icon: Send },
  { href: "/published", label: "Published", icon: FileCheck2 },
  { href: "/media-library", label: "Media Library", icon: FolderOpen },
  { href: "/sources", label: "Sources", icon: Newspaper },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/tasks", label: "My Tasks", icon: FileCheck2 },
  { href: "/account", label: "My Account", icon: Settings },
  { href: "/users", label: "User Management", icon: Settings },
  { href: "/audit", label: "Audit History", icon: FileCheck2 },
  { href: "/settings", label: "Settings", icon: Settings }
];
