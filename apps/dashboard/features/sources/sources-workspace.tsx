"use client";
import { useState } from "react";
import Link from "next/link";
import { Plus, Radio } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { CollectionRun, localDate, newsroom, Source, SourcePage, SourceTest } from "@/features/feeds/api";
import { Feedback, Status } from "@/features/feeds/shared";
import { useRemote } from "@/features/feeds/use-remote";
import { SourceForm } from "./source-form";

export function SourcesWorkspace() {
  const [cursor, setCursor] = useState<string | null>(null);
  const { data, error, refresh } = useRemote<SourcePage>(`sources${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, 10000);
  const [editing, setEditing] = useState<Source | "new" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  async function action(source: Source, kind: "test" | "collect" | "toggle") {
    setBusy(source.id); setActionError(null); setNotice(null);
    try {
      if (kind === "test") {
        const result = await newsroom<SourceTest>(`sources/${source.id}/test`, { method: "POST" });
        setNotice(`${source.publisher}: ${result.message}`);
      } else if (kind === "collect") {
        const result = await newsroom<{ job_id: string }>(`sources/${source.id}/collect`, { method: "POST" });
        setJobId(result.job_id); setNotice(`${source.publisher}: collection queued`);
      } else {
        await newsroom(`sources/${source.id}`, { method: "PATCH", body: { active: !source.active } });
        setNotice(`${source.publisher} ${source.active ? "deactivated" : "activated"}`);
      }
      refresh();
    } catch (error) { setActionError((error as Error).message); } finally { setBusy(null); }
  }
  return <><PageHeader title="Sources" description="Register publishers and permitted feeds, test availability, and control collection." action={<Button onClick={() => setEditing("new")}><Plus />Add source</Button>} />
    <Feedback error={error ?? actionError} message={notice} />
    {editing && <SourceForm key={typeof editing === "string" ? "new" : editing.id} source={editing === "new" ? undefined : editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); setNotice("Source saved. Collection runs on its schedule; use Collect now to start immediately."); refresh(); }} />}
    {jobId && <JobStatus jobId={jobId} onClose={() => { setJobId(null); refresh(); }} />}
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-sm"><span className="text-muted-foreground">{data ? `${data.total} registered sources` : "Loading source registry…"}</span><Button asChild variant="outline" size="sm"><Link href="/news-feeds"><Radio />Incoming stories</Link></Button></div>
    {data?.items.length === 0 && <EmptyState title="Add your first source" description="Enter a public RSS/Atom URL, discover a website’s advertised feeds, or register a manual reference." />}
    <div className="space-y-4">{data?.items.map(source => <Card key={source.id}><CardContent className="p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0 flex-1"><div className="mb-2 flex flex-wrap items-center gap-2"><h2 className="font-semibold">{source.publisher}</h2><Status>{source.source_type.replace("_", " ")}</Status><Status>{source.active ? source.health : "INACTIVE"}</Status></div><a href={source.url} target="_blank" rel="noreferrer" className="break-all text-sm text-primary underline underline-offset-2">{source.url}</a>{source.feed_url && source.feed_url !== source.url && <p className="mt-1 break-all text-xs text-muted-foreground">Feed · {source.feed_url}</p>}<p className="mt-3 text-xs text-muted-foreground">Every {source.polling_interval} minutes · {source.language.toUpperCase()} · {source.category || "Feed categories"} · {source.rights.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-muted-foreground">Last success: {localDate(source.last_success)} · Next collection: {source.can_collect ? localDate(source.next_collection_at) : "Disabled"}</p>{source.last_error && <p className="mt-3 text-sm text-amber-800">{source.last_error}</p>}{source.latest_run && <p className="mt-2 text-xs text-muted-foreground">{source.latest_run.status}: {source.latest_run.message}</p>}</div><div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" disabled={!!busy} onClick={() => setEditing(source)}>Edit</Button><Button variant="outline" size="sm" disabled={!!busy} onClick={() => action(source, "test")}>Test Source</Button><Button size="sm" disabled={!!busy || !source.can_collect} onClick={() => action(source, "collect")}>Collect now</Button><Button variant="ghost" size="sm" disabled={!!busy} onClick={() => action(source, "toggle")}>{source.active ? "Deactivate" : "Activate"}</Button></div></div></CardContent></Card>)}</div>
    {data && (cursor || data.next_cursor) && <div className="mt-5 flex gap-3"><Button variant="outline" disabled={!cursor} onClick={() => setCursor(null)}>First page</Button><Button variant="outline" disabled={!data.next_cursor} onClick={() => setCursor(data.next_cursor)}>Next sources</Button></div>}
  </>;
}

const jobFinished = (job: CollectionRun) => ["SUCCEEDED", "FAILED", "SKIPPED"].includes(job.status);
function JobStatus({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { data, error } = useRemote<CollectionRun>(`ingestion/jobs/${jobId}`, 2000, jobFinished);
  return <div className="mb-5 flex items-center justify-between gap-3 rounded-lg border bg-card p-4 text-sm" role="status"><span>{error ?? (data ? `${data.status} · ${data.message}` : "Loading collection status…")}</span><Button variant="ghost" size="sm" onClick={onClose}>Dismiss</Button></div>;
}
