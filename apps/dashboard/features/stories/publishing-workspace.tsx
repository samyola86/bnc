"use client";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Feedback } from "../feeds/shared";
import { localDate, newsroom } from "../feeds/api";
import { useRemote } from "../feeds/use-remote";
import { Platform, platforms } from "./story-details";

type Entry = { id: string; story_id: string; title: string; version: number; origin_item_id: string | null; destinations: Platform[]; scheduled_at: string | null; status: string; delivery_status: string };
export function PublishingWorkspace() {
  const { data, error, refresh } = useRemote<{ items: Entry[] }>("publishing/queue", 10000);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function cancel(id: string) {
    setBusy(true); setActionError(null);
    try { await newsroom(`publishing/queue/${id}/cancel`, { method: "POST" }); refresh(); }
    catch (e) { setActionError((e as Error).message); } finally { setBusy(false); }
  }
  return <><PageHeader title="Publishing" description="Review saved story revisions, destinations and requested publication times." />
    <Feedback error={error ?? actionError} />
    <p className="mb-6 rounded-lg border bg-muted p-4 text-sm leading-6">Queue entries and schedules are saved. External delivery awaits editorial approval and connected platform accounts; nothing is posted automatically. Editing a story cancels its queued revision. Send the updated revision again when ready.</p>
    <Card><CardContent className="overflow-x-auto p-0"><table className="w-full min-w-[700px] text-left text-sm"><thead className="border-b bg-muted/40"><tr>{["Story", "Destinations", "Dhaka time", "Status", "Actions"].map(label => <th key={label} className="p-4">{label}</th>)}</tr></thead><tbody>
      {data?.items.map(entry => <tr key={entry.id} className="border-b align-top"><td className="p-4 font-medium">{entry.title}<p className="mt-2 text-xs text-muted-foreground">Revision {entry.version}</p></td><td className="p-4">{entry.destinations.map(p => platforms[p]).join(", ")}</td><td className="p-4">{entry.scheduled_at ? localDate(entry.scheduled_at) : "Immediate queue"}</td><td className="p-4">{entry.status === "SCHEDULED" ? "Schedule saved" : "Queued"}<p className="mt-2 max-w-56 text-xs text-muted-foreground">{entry.delivery_status}</p></td><td className="space-y-2 p-4"><Button asChild size="sm" variant="outline"><Link href={entry.origin_item_id ? `/news-feeds/drafts/${entry.story_id}` : `/manual-writing/${entry.story_id}`}>Edit story</Link></Button><Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => cancel(entry.id)}>Cancel queue entry</Button></td></tr>)}
      {data && !data.items.length && <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">No queued stories. Use Send to publishing in the story editor.</td></tr>}
    </tbody></table>{!data && !error && <p className="p-6">Loading queue…</p>}</CardContent></Card>
  </>;
}
