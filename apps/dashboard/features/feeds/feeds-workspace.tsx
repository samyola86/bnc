"use client";
import { Fragment, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLink, Pin, RefreshCw, Settings2 } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Candidate, CandidatePage, CollectionSettings, Draft, localDate, newsroom, SourcePage } from "./api";
import { Field, Feedback, fieldClass, Status } from "./shared";
import { useRemote } from "./use-remote";
import { RankingForm } from "./ranking-form";

type Counter = { count: number; available: boolean; definition: string };
type Summary = Record<"incoming" | "original_drafts" | "awaiting_publication" | "published", Counter>;

export function FeedsWorkspace() {
  const router = useRouter();
  const [filters, setFilters] = useState({ status: "DISCOVERED", source: "", query: "", category: "", preferred: false, history: true });
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [sourceCursor, setSourceCursor] = useState<string | null>(null);
  const params = new URLSearchParams({ status: filters.status, query: filters.query, category: filters.category, include_inactive: String(filters.history), preferred_only: String(filters.preferred) });
  if (filters.source) params.set("source_id", filters.source);
  if (cursor) params.set("cursor", cursor);
  const { data, error, refresh } = useRemote<CandidatePage>(`feeds/items?${params}`, 10000);
  const { data: sources, error: sourcesError } = useRemote<SourcePage>(`sources?include_archived=true${sourceCursor ? `&cursor=${encodeURIComponent(sourceCursor)}` : ""}`, 30000);
  const { data: settings } = useRemote<CollectionSettings>("ingestion/settings", 30000);
  const { data: summary, error: summaryError, refresh: refreshSummary } = useRemote<Summary>("feeds/summary", 10000);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  function filter<K extends keyof typeof filters>(key: K, value: typeof filters[K]) { setFilters(previous => ({ ...previous, [key]: value })); setCursor(null); }
  async function edit(item: Candidate, body: unknown) {
    setBusy(item.id); setActionError(null);
    try { await newsroom(`feeds/items/${item.id}`, { method: "PATCH", body }); refresh(); refreshSummary(); }
    catch (error) { setActionError((error as Error).message); } finally { setBusy(null); }
  }
  async function openStory(item: Candidate) {
    setBusy(item.id); setActionError(null);
    try {
      const id = item.story_id ?? (await newsroom<Draft>(`feeds/items/${item.id}/draft`, { method: "POST" })).id;
      router.push(`/news-feeds/drafts/${id}`);
    } catch (error) { setActionError((error as Error).message); } finally { setBusy(null); }
  }
  return <><PageHeader title="Incoming Stories" description="Review source evidence, select candidates, and edit original BNC reporting." action={<Button asChild variant="outline"><Link href="/sources"><Settings2 />Manage sources</Link></Button>} />
    <Feedback error={error ?? actionError ?? sourcesError ?? summaryError} />
    <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{([["incoming", "Incoming"], ["original_drafts", "Original Drafts"], ["awaiting_publication", "Awaiting Publication"], ["published", "Published"]] as const).map(([key, label]) => <Card key={key}><CardContent className="p-5"><p className="text-xs font-semibold text-muted-foreground">{label}</p><p className="my-3 text-2xl font-bold">{summary ? summary[key].available ? summary[key].count : "Unavailable" : summaryError ? "Unavailable" : "…"}</p><p className="text-xs leading-5 text-muted-foreground">{summary?.[key].definition ?? "Loading database counts"}{summary && !summary[key].available ? ` (${summary[key].count} recorded)` : ""}</p></CardContent></Card>)}</div>
    <Card><CardContent className="p-0">
      <div className="flex items-center justify-between gap-3 border-b p-5"><div><h2 className="font-semibold">Editorial queue</h2><p className="mt-1 text-xs text-muted-foreground">{data ? `${data.total} matching stories · ${data.items.length} shown · up to ${data.candidate_limit} per batch` : "Loading candidates…"}</p></div><Button variant="outline" onClick={() => { setCursor(null); refresh(); refreshSummary(); }}><RefreshCw />Refresh Queue</Button></div>
      <div className="flex gap-2 overflow-x-auto border-b p-4" aria-label="Filter by source"><Button size="sm" variant={!filters.source ? "default" : "ghost"} aria-pressed={!filters.source} onClick={() => filter("source", "")}>All sources</Button>{sources?.items.map(source => <Button className="shrink-0" key={source.id} size="sm" variant={filters.source === source.id ? "default" : "ghost"} aria-pressed={filters.source === source.id} onClick={() => filter("source", source.id)}>{source.publisher}{source.archived_at ? " · Archived" : !source.active ? " · Inactive" : ""}</Button>)}</div>
      <div className="space-y-4 border-b p-5"><div className="grid items-end gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Editorial status"><select className={fieldClass} value={filters.status} onChange={e => filter("status", e.target.value)}><option value="DISCOVERED">Discovered</option><option value="SELECTED">Selected</option><option value="DRAFT">Draft</option><option value="DISMISSED">Dismissed</option><option value="all">All statuses</option></select></Field>
        <Field label="Source selector"><select className={fieldClass} value={filters.source} onChange={e => filter("source", e.target.value)}><option value="">All sources</option>{sources?.items.map(source => <option key={source.id} value={source.id}>{source.publisher}{source.archived_at ? " (archived)" : ""}</option>)}</select></Field>
        <Field label="Category"><input className={fieldClass} value={filters.category} maxLength={100} onChange={e => filter("category", e.target.value)} placeholder="Exact feed or saved draft category" /></Field>
        <form className="flex items-end gap-2" onSubmit={e => { e.preventDefault(); filter("query", search); }}><Field label="Search headlines"><input className={fieldClass} value={search} maxLength={200} onChange={e => setSearch(e.target.value)} placeholder="Headline keywords" /></Field><Button variant="outline" type="submit">Search</Button></form>
      </div><div className="flex flex-wrap items-center gap-5 text-xs"><label className="flex items-center gap-2"><input type="checkbox" checked={filters.history} onChange={e => filter("history", e.target.checked)} />Include inactive / archived source history</label><label className="flex items-center gap-2"><input type="checkbox" disabled={!settings?.preferred_categories.length} checked={filters.preferred} onChange={e => filter("preferred", e.target.checked)} />Preferred categories{settings?.preferred_categories.length ? `: ${settings.preferred_categories.join(", ")}` : " (configure in Sources)"}</label><Link className="text-primary underline" href="/sources">Collection settings</Link>{(sourceCursor || sources?.next_cursor) && <div className="flex gap-2">{sourceCursor && <Button size="sm" variant="ghost" onClick={() => setSourceCursor(null)}>First sources</Button>}{sources?.next_cursor && <Button size="sm" variant="ghost" onClick={() => setSourceCursor(sources.next_cursor)}>More sources</Button>}</div>}</div></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[1050px] text-left text-sm"><thead className="border-b bg-muted/40 text-xs uppercase text-muted-foreground"><tr>{["Story", "Category & Tags", "Users", "Status", "Actions"].map(label => <th scope="col" key={label} className="px-5 py-4 font-semibold">{label}</th>)}</tr></thead><tbody>
        {data?.items.map(item => <Fragment key={item.id}><tr className="border-b align-top hover:bg-muted/20">
          <td className="max-w-md space-y-2 px-5 py-5"><button className="text-left font-semibold leading-6 hover:text-primary hover:underline" disabled={!!busy} onClick={() => openStory(item)}>{item.draft_title ?? item.title}</button>{item.draft_title && item.draft_title !== item.title && <p className="text-xs text-muted-foreground">Feed headline: {item.title}</p>}<p className="text-xs text-muted-foreground">{item.publisher || "Publisher needs review"} · {localDate(item.published_at)}</p><p className="text-xs text-muted-foreground">{item.sources.map(s => `${s.publisher}${s.archived ? " (archived)" : !s.active ? " (inactive)" : ""}`).join(" · ")}</p><a href={item.original_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary underline">Original source<ExternalLink className="size-3" /></a><div className="flex items-center gap-2"><Button aria-label={item.pinned ? "Unpin candidate" : "Pin candidate"} variant={item.pinned ? "default" : "ghost"} size="sm" disabled={!!busy} onClick={() => edit(item, { pinned: !item.pinned })}><Pin className="size-3" />{item.pinned ? "Pinned" : "Pin"}</Button><span className="text-xs text-muted-foreground">Rank {item.score.toFixed(1)}</span></div></td>
          <td className="max-w-48 px-5 py-5"><Status>{(item.draft_category ?? item.category) || "Uncategorized"}</Status><div className="mt-3 flex flex-wrap gap-1">{item.tags.map(tag => <span className="rounded bg-muted px-2 py-1 text-xs" key={tag}>{tag}</span>)}{!item.tags.length && <span className="text-xs text-muted-foreground">No saved tags</span>}</div>{item.ai_assisted && <p className="mt-2 text-xs text-amber-800">AI-assisted · human review required</p>}</td>
          <td className="px-5 py-5 text-xs">{item.assigned_author ? <><p className="font-medium">{item.assigned_author.name}</p><p className="mt-1 text-muted-foreground">Story author</p></> : <span className="text-muted-foreground">Unassigned</span>}</td>
          <td className="px-5 py-5"><Status>{item.editorial_status}</Status></td>
          <td className="w-64 px-5 py-5"><div className="flex flex-wrap gap-2"><Button size="sm" disabled={!!busy} onClick={() => openStory(item)}>{busy === item.id ? "Working…" : "Edit Story"}</Button><Button size="sm" variant="outline" aria-expanded={reviewing === item.id} onClick={() => setReviewing(reviewing === item.id ? null : item.id)}>{reviewing === item.id ? "Close review" : "Review"}</Button>{!item.story_id && <><Button size="sm" variant="outline" disabled={!!busy} onClick={() => edit(item, { editorial_status: item.editorial_status === "SELECTED" ? "DISCOVERED" : "SELECTED" })}>{item.editorial_status === "SELECTED" ? "Deselect" : "Select"}</Button><Button size="sm" variant="ghost" disabled={!!busy} onClick={() => edit(item, { editorial_status: item.editorial_status === "DISMISSED" ? "DISCOVERED" : "DISMISSED" })}>{item.editorial_status === "DISMISSED" ? "Restore" : "Dismiss"}</Button></>}</div></td>
        </tr>{reviewing === item.id && <tr className="border-b bg-muted/20"><td colSpan={5} className="space-y-4 p-5"><p className="whitespace-pre-wrap leading-6">{item.excerpt || "No summary supplied by the feed."}</p><p className="text-xs text-muted-foreground">Source metadata is evidence, not verified BNC reporting. Full article text and publisher photographs are not imported. Ranking is an editorial heuristic, not factual verification.</p><div className="grid gap-3 md:grid-cols-2">{item.attributions.map((credit, index) => <div key={`${credit.source_id}-${index}`} className="rounded border bg-card p-3 text-xs leading-5"><p className="font-semibold">{credit.publisher_name} · {credit.rights_status.replaceAll("_", " ")}</p><a href={credit.original_url} target="_blank" rel="noreferrer" className="break-all text-primary underline">{credit.original_url}</a><p>Published {localDate(credit.published_at)} · Retrieved {localDate(credit.retrieved_at)}</p></div>)}</div><RankingForm item={item} disabled={!!busy} onSave={body => edit(item, body)} /></td></tr>}</Fragment>)}
        {data?.items.length === 0 && <tr><td colSpan={5} className="p-10 text-center text-muted-foreground">No candidates match this view. Change filters or use Sources → Collect now to fetch real metadata.</td></tr>}
      </tbody></table></div>
      <div className="flex flex-wrap items-center justify-between gap-3 p-5 text-xs text-muted-foreground"><span>Dates shown in Asia/Dhaka. Refresh Queue reloads stored candidates; collection runs from Sources.</span><div className="flex gap-2"><Button size="sm" variant="outline" disabled={!cursor} onClick={() => setCursor(null)}>First batch</Button><Button size="sm" disabled={!data?.next_cursor} onClick={() => { setCursor(data?.next_cursor ?? null); setReviewing(null); }}>Next batch</Button></div></div>
    </CardContent></Card>
  </>;
}
