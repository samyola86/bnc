"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLink, Pin, RefreshCw, Settings2 } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/empty-state";
import { Candidate, CandidatePage, Draft, localDate, newsroom, SourcePage } from "./api";
import { Field, Feedback, fieldClass, Status } from "./shared";
import { useRemote } from "./use-remote";

export function FeedsWorkspace() {
  const router = useRouter();
  const [filters, setFilters] = useState({ status: "DISCOVERED", source: "", query: "", category: "" });
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const params = new URLSearchParams({ status: filters.status, query: filters.query, category: filters.category });
  if (filters.source) params.set("source_id", filters.source);
  if (cursor) params.set("cursor", cursor);
  const { data, error, refresh } = useRemote<CandidatePage>(`feeds/items?${params}`, 10000);
  const { data: sources } = useRemote<SourcePage>("sources", 30000);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  function filter(key: keyof typeof filters, value: string) { setFilters(previous => ({ ...previous, [key]: value })); setCursor(null); }
  async function edit(item: Candidate, body: unknown) {
    setBusy(item.id); setActionError(null);
    try { await newsroom(`feeds/items/${item.id}`, { method: "PATCH", body }); refresh(); }
    catch (error) { setActionError((error as Error).message); } finally { setBusy(null); }
  }
  async function draft(item: Candidate) {
    setBusy(item.id); setActionError(null);
    try {
      const created = await newsroom<Draft>(`feeds/items/${item.id}/draft`, { method: "POST" });
      router.push(`/news-feeds/drafts/${created.id}`);
    } catch (error) { setActionError((error as Error).message); } finally { setBusy(null); }
  }
  async function limit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setActionError(null);
    const count = Number(new FormData(event.currentTarget).get("limit"));
    try {
      await newsroom("ingestion/settings", { method: "PATCH", body: { candidate_limit: count } });
      setCursor(null); refresh(); setNotice(`Candidate batches now contain up to ${count} stories.`);
    } catch (error) { setActionError((error as Error).message); }
  }
  return <><PageHeader title="News Feeds" description="Review real feed metadata, keep source provenance, and select stories for original reporting." action={<Button asChild variant="outline"><Link href="/sources"><Settings2 />Manage sources</Link></Button>} />
    <Feedback error={error ?? actionError} message={notice} />
    <Card className="mb-5"><CardContent className="p-5"><div className="grid items-end gap-3 md:grid-cols-4"><Field label="Editorial status"><select className={fieldClass} value={filters.status} onChange={e => filter("status", e.target.value)}><option value="DISCOVERED">Discovered</option><option value="SELECTED">Selected</option><option value="DRAFT">Draft created</option><option value="DISMISSED">Dismissed</option><option value="all">All statuses</option></select></Field><Field label="Publisher"><select className={fieldClass} value={filters.source} onChange={e => filter("source", e.target.value)}><option value="">All active sources</option>{sources?.items.map(source => <option key={source.id} value={source.id}>{source.publisher}{!source.active ? " (inactive)" : ""}</option>)}</select></Field><Field label="Category"><input className={fieldClass} value={filters.category} maxLength={100} onChange={e => filter("category", e.target.value)} placeholder="Exact feed category" /></Field><form className="flex items-end gap-2" onSubmit={e => { e.preventDefault(); filter("query", search); }}><Field label="Search headlines"><input className={fieldClass} value={search} maxLength={200} onChange={e => setSearch(e.target.value)} placeholder="Headline keywords" /></Field><Button variant="outline" type="submit">Search</Button></form></div>
      <div className="mt-5 flex flex-wrap items-end justify-between gap-3 border-t pt-4"><form onSubmit={limit} className="flex items-end gap-2" key={data?.candidate_limit ?? "loading"}><Field label="Stories per batch (20–50)"><input className={fieldClass} type="number" min={20} max={50} name="limit" defaultValue={data?.candidate_limit ?? 30} required /></Field><Button variant="outline" type="submit">Apply</Button></form><Button variant="ghost" onClick={refresh}><RefreshCw />Refresh queue</Button></div>
      <p className="mt-4 text-xs leading-5 text-muted-foreground">Ranking is a configurable editorial heuristic. Relevance and impact begin at neutral values; corroboration begins at zero. Multiple syndicated copies do not establish independent verification. Dates are shown in Asia/Dhaka.</p>
    </CardContent></Card>
    <p className="mb-4 text-sm text-muted-foreground">{data ? `${data.total} matching stories · showing ${data.items.length} in this batch` : "Loading candidates…"}</p>
    {data?.items.length === 0 && <EmptyState title="No candidates match this view" description="Add an active feed in Sources and use Collect now, or wait for scheduled collection. You can also change the status, publisher, or category filters." />}
    <div className="space-y-4">{data?.items.map(item => <Card key={item.id}><CardContent className="p-5"><div className="flex items-start gap-3"><div className="min-w-0 flex-1"><div className="mb-2 flex flex-wrap items-center gap-2"><Status>{item.editorial_status}</Status><Status>{item.category || "Uncategorized"}</Status>{item.pinned && <Status>Pinned</Status>}<span className="text-xs text-muted-foreground">Score {item.score.toFixed(1)}</span></div><h2 className="text-lg font-semibold leading-7">{item.title}</h2><p className="mt-2 text-xs text-muted-foreground">{item.publisher || "Publisher needs review"} · {localDate(item.published_at)}{item.author ? ` · ${item.author}` : ""}</p><a href={item.original_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex max-w-full items-center gap-1 break-all text-sm text-primary underline underline-offset-2">Original story<ExternalLink className="size-3 shrink-0" /></a>{item.attributions.length > 1 && <p className="mt-2 text-xs text-muted-foreground">{item.attributions.length} feed records retained for attribution; one candidate.</p>}</div><Button aria-label={item.pinned ? "Unpin candidate" : "Pin candidate"} variant={item.pinned ? "default" : "ghost"} size="sm" disabled={!!busy} onClick={() => edit(item, { pinned: !item.pinned })}><Pin /></Button></div>
      <div className="mt-4 flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => setReviewing(reviewing === item.id ? null : item.id)}>{reviewing === item.id ? "Close details" : "Review metadata & ranking"}</Button>{item.story_id ? <Button asChild size="sm"><Link href={`/news-feeds/drafts/${item.story_id}`}>Open draft</Link></Button> : <><Button size="sm" disabled={!!busy} onClick={() => draft(item)}>Create draft</Button><Button variant="outline" size="sm" disabled={!!busy} onClick={() => edit(item, { editorial_status: item.editorial_status === "SELECTED" ? "DISCOVERED" : "SELECTED" })}>{item.editorial_status === "SELECTED" ? "Return to discovered" : "Select"}</Button><Button variant="ghost" size="sm" disabled={!!busy} onClick={() => edit(item, { editorial_status: item.editorial_status === "DISMISSED" ? "DISCOVERED" : "DISMISSED" })}>{item.editorial_status === "DISMISSED" ? "Restore" : "Dismiss"}</Button></>}</div>
      {reviewing === item.id && <div className="mt-5 space-y-4 border-t pt-5"><p className="whitespace-pre-wrap text-sm leading-6">{item.excerpt || "No summary supplied by the feed."}</p><p className="text-xs text-muted-foreground">Feed metadata is source material, not a verified BNC article. Full article text and publisher photographs are not fetched.</p><div className="space-y-2">{item.attributions.map((credit, index) => <div key={`${credit.source_id}-${index}`} className="rounded-lg bg-muted p-3 text-xs"><p className="font-semibold">{credit.publisher_name} · {credit.rights_status.replaceAll("_", " ")}</p><a href={credit.original_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-primary underline">{credit.original_url}</a><p className="mt-1">Retrieved {localDate(credit.retrieved_at)}</p></div>)}</div><RankingForm item={item} disabled={!!busy} onSave={body => edit(item, body)} /></div>}
    </CardContent></Card>)}</div>
    {data && (cursor || data.next_cursor) && <div className="mt-6 flex gap-3"><Button variant="outline" disabled={!cursor} onClick={() => setCursor(null)}>First batch</Button><Button disabled={!data.next_cursor} onClick={() => { setCursor(data.next_cursor); setReviewing(null); }}>Next batch</Button></div>}
  </>;
}

function RankingForm({ item, disabled, onSave }: { item: Candidate; disabled: boolean; onSave: (body: unknown) => void }) {
  return <form className="grid items-end gap-3 sm:grid-cols-2 xl:grid-cols-5" onSubmit={event => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const body: Record<string, number | null> = {};
    for (const key of ["bangladesh_relevance", "public_impact", "corroboration", "uniqueness", "rank_override"] as const) body[key] = data.get(key) === "" ? null : Number(data.get(key));
    onSave(body);
  }}>{([["bangladesh_relevance", "Bangladesh relevance"], ["public_impact", "Public impact"], ["corroboration", "Verified corroboration"], ["uniqueness", "Uniqueness"], ["rank_override", "Score override (optional)"]] as const).map(([key, label]) => <Field key={key} label={label}><input type="number" name={key} min={0} max={100} required={key !== "rank_override"} className={fieldClass} defaultValue={item[key] ?? ""} /></Field>)}<Button type="submit" variant="outline" size="sm" disabled={disabled}>Save ranking</Button></form>;
}
