"use client";
import Link from "next/link";
import { useRemote } from "../feeds/use-remote";
import { Feedback } from "../feeds/shared";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function SystemSettings() {
  const { data, error } = useRemote<Record<string, boolean | number | string | null>>("admin/system-status");
  return <><PageHeader title="System Settings" description="Superadmin configuration and security status. Credentials remain in the backend deployment environment." /><Feedback error={error} /><div className="mb-6 flex flex-wrap gap-3">{[["/users", "Manage users"], ["/tasks", "Assignments"], ["/sources", "Collection settings"], ["/audit", "Audit history"], ["/account", "My account security"]].map(([href, label]) => <Button asChild variant="outline" key={href}><Link href={href}>{label}</Link></Button>)}</div><Card><CardContent className="p-6"><dl className="grid gap-4 sm:grid-cols-2">{data && Object.entries(data).map(([key, value]) => <div key={key} className="border-b pb-3"><dt className="text-xs capitalize text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="mt-1 break-words text-sm font-medium">{typeof value === "boolean" ? value ? "Yes" : "No" : value ?? "Not configured"}</dd></div>)}</dl><p className="mt-6 text-sm leading-6 text-muted-foreground">Change AI, SMTP, encryption-key and production HTTPS settings through the trusted API/worker deployment environment, then recreate services. This screen never returns passwords, session identifiers or API keys. External platform delivery is disabled in this phase.</p></CardContent></Card></>;
}
