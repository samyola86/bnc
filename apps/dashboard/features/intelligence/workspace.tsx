"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Field, Feedback, fieldClass } from "../feeds/shared";
import { newsroom, localDate, type Draft, type SourcePage } from "../feeds/api";
import { useRemote } from "../feeds/use-remote";
import { useSession } from "../accounts/session";
import type { Account } from "../accounts/session";

type Trend = { id: string; title: string; category: string; tags: string[]; score: number; momentum: number; confidence: number; pinned: boolean; last_activity: string; analysis_at: string; representative_item_id: string | null; signals: { count: number; baseline_count: number; direction: string; publisher_count: number; publishers: string[]; evidence_quality: number; explanation: string; warnings: string[]; factors: Record<string, number>; google_trends: unknown; instagram_engagement: Record<string, unknown>[] | null }; sources: { item_id: string; publisher: string; url: string; provider: string; rights: string; eligible: boolean; unresolved_redirect: boolean }[]; items: { id: string; title: string; url: string }[]; history?: { at: string; momentum: number; score: number }[] };

export function IntelligenceWorkspace({ clusterId, recommendations = false }: { clusterId?: string; recommendations?: boolean }) {
  const [window, setWindow] = useState("24h");
  const [category, setCategory] = useState("");
  const [geography, setGeography] = useState("all");
  const [query, setQuery] = useState("");
  const [order, setOrder] = useState("priority");
  const [unreviewed, setUnreviewed] = useState(false);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { user } = useSession();
  const editor = user?.role === "EDITOR" || user?.role === "SUPERADMIN";
  const params = new URLSearchParams({ window, category, geography, query, order, unreviewed: String(unreviewed), needs_verification: String(needsVerification), offset: String(offset) });
  const { data, error: loadError, refresh } = useRemote<{ items: Trend[]; total: number; next_offset: number | null } & Trend>(clusterId ? `intelligence/trends/${clusterId}?window=${window}` : `intelligence/${recommendations ? "recommendations" : "trends"}?${params}`, 60000);
  const router = useRouter();
  async function act(trend: Trend, action: string, body?: unknown) {
    setError(null); setBusy(true);
    try {
      if (action === "draft") {
        const draft = await newsroom<Draft>(`intelligence/trends/${trend.id}/draft`, { method: "POST" });
        router.push(`/news-feeds/drafts/${draft.id}`);
      } else {
        await newsroom(`intelligence/trends/${trend.id}${action === "edit" ? "" : `/${action}`}`, { method: action === "edit" ? "PATCH" : "POST", body });
        setNotice(action === "select" ? "Added to Incoming Stories → Selected." : "Editorial decision saved."); refresh();
      }
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const trends = clusterId ? data ? [data] : [] : data?.items ?? [];
  return <><PageHeader title={clusterId ? "Trend detail" : recommendations ? "Recommended for Publishing" : "Trending Stories"} description="Machine-generated discovery leads. Coverage momentum is not public popularity, verification, or editorial approval." />
    <div className="mb-5 flex flex-wrap gap-4 text-sm underline"><Link href="/trending">Trending Now</Link><Link href="/recommendations">Recommended for Publishing</Link><Link href="/news-feeds">Incoming Stories</Link>{user?.role === "SUPERADMIN" && <Link href="/intelligence-settings">AI Intelligence Settings</Link>}</div>
    <div className="mb-5 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-3 lg:grid-cols-4">
      <Field label="Trend window"><select className={fieldClass} value={window} onChange={e => { setWindow(e.target.value); setOffset(0); }}>{["1h", "6h", "24h", "7d"].map(v => <option key={v}>{v}</option>)}</select></Field>
      {!clusterId && <><Field label="Geography"><select className={fieldClass} value={geography} onChange={e => { setGeography(e.target.value); setOffset(0); }}><option value="all">All trends</option><option value="BD">Bangladesh Trends</option><option value="global">Global Trends</option></select></Field><Field label="Category"><input className={fieldClass} placeholder="e.g. Technology" value={category} onChange={e => { setCategory(e.target.value); setOffset(0); }} /></Field><Field label="Search topics"><input className={fieldClass} value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} /></Field><Field label="Sort"><select className={fieldClass} value={order} onChange={e => setOrder(e.target.value)}><option value="priority">Highest priority</option><option value="momentum">Fastest rising</option></select></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unreviewed} onChange={e => setUnreviewed(e.target.checked)} />Unreviewed</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={needsVerification} onChange={e => setNeedsVerification(e.target.checked)} />Needs verification</label></>}
      <Button variant="outline" onClick={refresh}>Refresh</Button>
    </div>
    <Feedback error={error ?? loadError} message={notice} />
    {!data && !loadError && <p role="status">Loading news intelligence…</p>}
    {data && !trends.length && <div className="rounded-lg border bg-card p-8"><h2 className="font-semibold">No matching trends yet</h2><p className="mt-2 text-sm text-muted-foreground">Eligible collected headlines will appear after the next intelligence cycle. Check Sources and provider health if collection is unavailable.</p></div>}
    <div className="space-y-5">{trends.map(trend => <article key={trend.id} className="rounded-lg border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs uppercase text-muted-foreground">{trend.category} · machine-generated · {trend.signals.direction}</p><h2 className="text-lg font-semibold"><Link href={`/trending/${trend.id}`}>{trend.title}</Link></h2><p className="mt-2 text-sm">{trend.tags.join(" · ")}</p></div><div className="text-right"><strong className="text-3xl text-primary">{trend.score.toFixed(1)}</strong><p className="text-xs">priority / 100</p></div></div>
      <div className="my-4 flex flex-wrap gap-5 text-sm"><span>Momentum {trend.momentum}/100</span><span>{trend.signals.publisher_count} publishers</span><span>Evidence quality {trend.signals.evidence_quality}/100</span><span>Bangladesh relevance {trend.signals.factors.bangladesh_relevance ?? "Unavailable"}</span></div>
      <p className="text-sm">{trend.signals.explanation}</p><p className="mt-2 text-xs text-muted-foreground">Last activity {localDate(trend.last_activity)} · Analysis {localDate(trend.analysis_at)}</p>
      <details className="mt-4"><summary className="cursor-pointer text-sm font-medium">Evidence, score explanation and limitations</summary><ul className="my-3 space-y-1 text-xs text-amber-800">{trend.signals.warnings.map(w => <li key={w}>{w}</li>)}</ul><dl className="grid gap-2 text-sm sm:grid-cols-2">{Object.entries(trend.signals.factors).map(([key, value]) => <div key={key}>{key.replaceAll("_", " ")}: {value.toFixed(1)}</div>)}</dl><p className="mt-3 text-sm">Search interest: unavailable · Independent confirmations: not established</p><p className="mt-2 text-sm">Instagram signals: {trend.signals.instagram_engagement ? JSON.stringify(trend.signals.instagram_engagement) : "Unavailable"}</p><ul className="mt-3 space-y-2 text-sm">{trend.sources.map((source, i) => <li key={i}><a href={source.url} target="_blank" rel="noreferrer" className="underline">{source.publisher || "Publisher not supplied"}</a> · {source.provider} · {source.rights}{source.unresolved_redirect && " · Google redirect; original URL unresolved"}{!source.eligible && " · Ineligible source"}</li>)}</ul></details>
      <div className="mt-5 flex flex-wrap gap-3"><Button disabled={busy || !trend.representative_item_id} onClick={() => act(trend, "draft")}>Create / open draft</Button>{editor && <><Button variant="outline" disabled={busy} onClick={() => act(trend, "select")}>Add to discovery queue</Button><Button variant="outline" disabled={busy} onClick={() => act(trend, "edit", { pinned: !trend.pinned })}>{trend.pinned ? "Unpin" : "Pin"}</Button><Button variant="ghost" disabled={busy} onClick={() => act(trend, "edit", { dismissed: true })}>Dismiss</Button></>}</div>
      {clusterId && <><h3 className="mt-6 font-semibold">Related coverage</h3><ul className="mt-3 space-y-2 text-sm">{trend.items.map(item => <li key={item.id}><a className="underline" href={item.url} rel="noreferrer" target="_blank">{item.title}</a></li>)}</ul><h3 className="mt-6 font-semibold">Trend history</h3>{!trend.history?.length ? <p className="mt-2 text-sm">No stored snapshots yet.</p> : <table className="mt-3 w-full text-left text-sm"><thead><tr><th>Observed</th><th>Momentum</th><th>Priority</th></tr></thead><tbody>{trend.history.map(h => <tr key={h.at}><td>{localDate(h.at)}</td><td>{h.momentum}</td><td>{h.score}</td></tr>)}</tbody></table>}{editor && <EditorialControls trend={trend} refresh={refresh} />}{user?.role === "SUPERADMIN" && <Assignment trend={trend} />}</>}
    </article>)}</div>{editor && !clusterId && <ManualInstagramLead />}
    {!clusterId && data && <div className="mt-5 flex gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</Button><span className="p-2 text-sm">{data.total} matching clusters</span><Button variant="outline" disabled={data.next_offset === null} onClick={() => setOffset(data.next_offset ?? 0)}>Next</Button></div>}
  </>;
}

function EditorialControls({ trend, refresh }: { trend: Trend; refresh: () => void }) {
  const [score, setScore] = useState(""); const [category, setCategory] = useState(trend.category); const [tags, setTags] = useState(trend.tags.join(", ")); const [selected, setSelected] = useState<string[]>([]); const [target, setTarget] = useState(""); const [error, setError] = useState<string | null>(null);
  async function save(action: string) { try { setError(null); if (action === "score") await newsroom(`intelligence/trends/${trend.id}`, { method: "PATCH", body: { score_override: score === "" ? null : Number(score) } }); if (action === "classification") await newsroom(`intelligence/items/${trend.representative_item_id}/classification`, { method: "PATCH", body: { primary_category: category, tags: tags.split(",").map(v => v.trim()).filter(Boolean) } }); if (action === "move") await newsroom(`intelligence/trends/${trend.id}/move`, { method: "POST", body: { item_ids: selected, target_cluster_id: target || null } }); refresh(); } catch (e) { setError((e as Error).message); } }
  return <details className="mt-6 rounded border p-4"><summary className="cursor-pointer font-medium">Editorial corrections</summary><Feedback error={error} /><div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="Priority override (blank clears)"><input type="number" min={0} max={100} className={fieldClass} value={score} onChange={e => setScore(e.target.value)} /></Field><Button variant="outline" onClick={() => save("score")}>Save priority</Button><Field label="Correct category"><input className={fieldClass} value={category} onChange={e => setCategory(e.target.value)} /></Field><Field label="Correct tags"><input className={fieldClass} value={tags} onChange={e => setTags(e.target.value)} /></Field><Button variant="outline" onClick={() => save("classification")}>Save classification</Button></div><p className="my-3 text-sm">Select coverage to split into a new cluster, or enter a target cluster ID to merge it.</p>{trend.items.map(i => <label key={i.id} className="mb-2 flex gap-2 text-sm"><input type="checkbox" checked={selected.includes(i.id)} onChange={e => setSelected(e.target.checked ? [...selected, i.id] : selected.filter(id => id !== i.id))} />{i.title}</label>)}<Field label="Target cluster ID (blank creates a new cluster)"><input className={fieldClass} value={target} onChange={e => setTarget(e.target.value)} /></Field><Button className="mt-3" disabled={!selected.length} onClick={() => save("move")}>Move selected coverage</Button></details>;
}

function Assignment({ trend }: { trend: Trend }) {
  const { data } = useRemote<{ items: Account[] }>("admin/users"); const [assignee, setAssignee] = useState(""); const [message, setMessage] = useState<string | null>(null); const [error, setError] = useState<string | null>(null);
  async function assign() { try { const draft = await newsroom<Draft>(`intelligence/trends/${trend.id}/draft`, { method: "POST" }); await newsroom("tasks", { method: "POST", body: { title: trend.title.slice(0, 200), description: "Investigate this machine-generated discovery lead. Verify original evidence before submission.", assignee_id: assignee, story_id: draft.id } }); setMessage("Assignment created in My Tasks."); } catch (e) { setError((e as Error).message); } }
  return <div className="mt-5 rounded border p-4"><Feedback error={error} message={message} /><Field label="Assign reporting through existing tasks"><select className={fieldClass} value={assignee} onChange={e => setAssignee(e.target.value)}><option value="">Select an active writer or editor</option>{data?.items.filter(u => u.active && ["EDITOR", "CONTENT_WRITER"].includes(u.role)).map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field><Button className="mt-3" disabled={!assignee} onClick={assign}>Create assignment</Button></div>;
}

export function ManualInstagramLead() {
  const { data } = useRemote<SourcePage>("sources?include_archived=false"); const [source, setSource] = useState(""); const [url, setUrl] = useState(""); const [title, setTitle] = useState(""); const [caption, setCaption] = useState(""); const [error, setError] = useState<string | null>(null); const [message, setMessage] = useState<string | null>(null);
  return <form className="mt-5 space-y-4 rounded border bg-card p-5" onSubmit={async e => { e.preventDefault(); try { const result = await newsroom<{ inserted: number; warning: string }>(`intelligence/sources/${source}/instagram-post`, { method: "POST", body: { url, title, caption } }); setMessage(`${result.inserted} new lead. ${result.warning}`); setError(null); } catch (error) { setError((error as Error).message); } }}><h2 className="font-semibold">Manual Instagram reporting lead</h2><p className="text-sm text-muted-foreground">Paste a public post link and permitted metadata. BNC does not scrape Instagram.</p><Feedback error={error} message={message} /><Field label="Instagram source"><select required className={fieldClass} value={source} onChange={e => setSource(e.target.value)}><option value="">Choose a registered account</option>{data?.items.filter(s => s.source_type === "INSTAGRAM_ACCOUNT").map(s => <option key={s.id} value={s.id}>{s.publisher}</option>)}</select></Field><Field label="Post permalink"><input type="url" required className={fieldClass} value={url} onChange={e => setUrl(e.target.value)} /></Field><Field label="Lead headline"><input required maxLength={500} className={fieldClass} value={title} onChange={e => setTitle(e.target.value)} /></Field><Field label="Permitted caption / notes"><textarea maxLength={1200} className={fieldClass} value={caption} onChange={e => setCaption(e.target.value)} /></Field><Button>Save unverified lead</Button></form>;
}
