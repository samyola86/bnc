import type { ReactNode } from "react";
export function PageHeader({ eyebrow = "EDITORIAL WORKSPACE", title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-primary">{eyebrow}</p><h1 className="text-3xl font-bold tracking-tight">{title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></div>{action}</div>;
}
