import type { Metadata } from "next";
import { Sidebar } from "@/components/layout/sidebar";
import "./globals.css";
export const metadata: Metadata = { title: { default: "Overview | BNC Newsroom", template: "%s | BNC Newsroom" }, description: "Bangladesh News Corporation editorial dashboard" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:z-50 focus:bg-card focus:p-4">Skip to content</a><Sidebar /><div className="lg:pl-64"><header className="flex min-h-20 items-center justify-between gap-3 border-b bg-card px-6 lg:px-10"><p className="text-sm font-medium">Newsroom dashboard <span lang="bn" className="ml-2 text-muted-foreground">/ সংবাদকক্ষ</span></p><span className="rounded-full border px-3 py-1 text-xs text-muted-foreground">Asia/Dhaka · Local</span></header><main id="main-content" className="mx-auto max-w-7xl p-6 lg:p-10">{children}</main><footer className="px-6 pb-6 text-xs text-muted-foreground lg:px-10">BNC · Human-reviewed journalism. Independent delivery for every channel.</footer></div></body></html>;
}
