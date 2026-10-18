"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { navigation } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  return <aside className="border-b bg-card lg:fixed lg:inset-y-0 lg:left-0 lg:w-64 lg:border-r">
    <Link href="/" className="flex items-center gap-3 px-6 py-7" aria-label="BNC newsroom home">
      <span className="rounded bg-primary px-3 py-2 text-2xl font-black tracking-tighter text-white">BNC</span>
      <span className="text-sm font-semibold">Newsroom<span className="block text-xs font-normal text-muted-foreground">Bangladesh News Corporation</span></span>
    </Link>
    <nav aria-label="Main navigation" className="flex gap-1 overflow-x-auto px-3 pb-4 lg:flex-col">
      {navigation.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined} className={cn("flex shrink-0 items-center gap-3 rounded-md px-3 py-3 text-sm font-medium text-muted-foreground hover:bg-muted", pathname === href && "bg-primary/8 text-primary")}><Icon className="size-4" aria-hidden="true" />{label}</Link>)}
    </nav>
    <div className="m-5 hidden rounded-lg border bg-background p-4 text-xs leading-5 text-muted-foreground lg:absolute lg:bottom-0 lg:block"><span className="mb-1 block font-semibold text-foreground">Local development</span>Editorial workspace foundation.<br />External connections are inactive.</div>
  </aside>;
}
