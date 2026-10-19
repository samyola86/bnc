"use client";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Feedback, Field, fieldClass } from "../feeds/shared";
import { Draft, localDate, newsroom } from "../feeds/api";
import { useRemote } from "../feeds/use-remote";
import { Platform, platforms, detailsFrom } from "./story-details";
import { StoryPreview } from "./story-preview";
import { useSession } from "../accounts/session";

type Entry = { id: string; story_id: string; title: string; version: number; version_id: string; origin_item_id: string | null; destinations: Platform[]; scheduled_at: string | null; status: string; delivery_status: string; submitter: string; submitter_id: string | null; reviewer: string | null; decided_at: string | null; review_notes: string; contributors: string[]; format: string; warnings: string[]; created_at: string };
type Review = { request: Entry; draft: Draft; history: { decision: string; actor: string; notes: string; created_at: string; self_approval_override: boolean }[] };
const views = { IN_REVIEW: "Awaiting Review", CHANGES_REQUESTED: "Changes Requested", APPROVED: "Approved", READY: "Ready for Delivery", REJECTED: "Rejected", WITHDRAWN: "Withdrawn", QUEUED: "Legacy Queue", SCHEDULED: "Legacy Schedules", all: "Review History" };
export function PublishingWorkspace() {
  const [status, setStatus] = useState("IN_REVIEW");
  const { data, error } = useRemote<{ items: Entry[] }>(`publishing/queue?status=${status}`, 10000);
  return <><PageHeader title="Publishing & Editorial Review" description="Review an exact saved revision, record decisions and authorize readiness for future delivery." />
    <p className="mb-5 rounded-lg border bg-muted p-4 text-sm leading-6">READY authorizes an approved revision for future delivery. No WordPress or social post is sent in this phase. Editing approved content invalidates its approval.</p>
    <div className="mb-5 flex flex-wrap gap-2">{Object.entries(views).map(([key, label]) => <Button size="sm" key={key} variant={key === status ? "default" : "outline"} onClick={() => setStatus(key)}>{label}</Button>)}</div><Feedback error={error} />
    <Card><CardContent className="overflow-x-auto p-0"><table className="w-full min-w-[950px] text-left text-sm"><thead className="border-b bg-muted/40"><tr>{["Story / contributors", "Revision / submission", "Destinations / Dhaka time", "Decision", "Actions"].map(label => <th key={label} className="p-4">{label}</th>)}</tr></thead><tbody>{data?.items.map(entry => <tr key={entry.id} className="border-b align-top"><td className="p-4 font-medium">{entry.title}<p className="mt-2 text-xs text-muted-foreground">{entry.contributors.join(", ") || "No byline"} · {entry.format.replaceAll("_", " ")}</p>{entry.warnings.map(w => <p key={w} className="mt-2 text-xs text-amber-900">⚠ {w}</p>)}</td><td className="p-4">Revision {entry.version}<p className="mt-2 text-xs text-muted-foreground">Submitted by {entry.submitter}<br />{localDate(entry.created_at)}</p></td><td className="p-4">{entry.destinations.map(p => platforms[p]).join(", ")}<p className="mt-2 text-xs">{entry.scheduled_at ? localDate(entry.scheduled_at) : "No schedule requested"}</p></td><td className="p-4">{entry.status.replaceAll("_", " ")}<p className="mt-2 text-xs text-muted-foreground">{entry.reviewer ? `Reviewer: ${entry.reviewer}` : "No decision yet"}<br />{entry.review_notes}</p></td><td className="p-4"><Button asChild size="sm" variant="outline"><Link href={`/publishing/${entry.id}`}>Open review</Link></Button></td></tr>)}{data && !data.items.length && <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">No matching submissions.</td></tr>}</tbody></table></CardContent></Card>
  </>;
}

export function ReviewWorkspace({ id }: { id: string }) {
  const { user } = useSession();
  const { data, error, refresh } = useRemote<Review>(`publishing/requests/${id}`);
  const [notes, setNotes] = useState("");
  const [override, setOverride] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function decide(action: string) {
    if (!data) return;
    if (["request-changes", "reject"].includes(action) && !notes.trim()) { setActionError("Give an editorial reason in Review notes."); return; }
    if (override && !window.confirm("Record an explicit Superadmin self-approval exception with these notes?")) return;
    setBusy(true); setActionError(null);
    try {
      const path = action === "withdraw" ? `publishing/queue/${id}/cancel` : `stories/${data.request.story_id}/${action}`;
      await newsroom(path, { method: "POST", body: { request_id: id, base_version: data.request.version, notes, self_approval_override: override } }); refresh();
    } catch (e) { setActionError((e as Error).message); } finally { setBusy(false); }
  }
  if (!data) return <><Feedback error={error} /><p>Loading submitted revision…</p></>;
  const { request: entry, draft, history } = data;
  const reviewer = user?.role === "SUPERADMIN" || user?.role === "EDITOR";
  return <><PageHeader title={`Review: ${entry.title}`} description={`Exact revision ${entry.version} · ${entry.status.replaceAll("_", " ")} · Submitted by ${entry.submitter}`} action={<Button asChild variant="outline"><Link href="/publishing">Back to review queue</Link></Button>} /><Feedback error={error ?? actionError} />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]"><div className="space-y-5"><StoryPreview title={draft.title} summary={draft.summary} body={draft.body} category={draft.category} tags={draft.tags ?? []} language={draft.language} credits={draft.credits} details={detailsFrom(draft)} />
    {(draft.human_review_required || draft.editorial_warnings?.length || draft.claims_to_verify?.length) && <Card><CardContent className="p-5"><h2 className="font-semibold">AI verification warnings</h2><ul className="mt-3 list-disc pl-5 text-sm">{[...(draft.editorial_warnings ?? []), ...(draft.claims_to_verify ?? [])].map((w, i) => <li key={i}>{w}</li>)}</ul></CardContent></Card>}
    <Card><CardContent className="space-y-3 p-5"><h2 className="font-semibold">Original source provenance</h2>{draft.provenance.map((p, i) => <div key={i} className="break-words text-sm"><p>{p.publisher_name} · {p.rights_status}</p><a href={p.original_url} className="text-primary underline" target="_blank" rel="noreferrer">{p.original_url}</a><p className="text-xs">Published {localDate(p.published_at)} · Retrieved {localDate(p.retrieved_at)}</p></div>)}{!draft.provenance.length && <p className="text-sm">Independently authored reporting.</p>}</CardContent></Card>
    <Card><CardContent className="space-y-3 p-5"><h2 className="font-semibold">Decision history</h2>{history.map((h, i) => <div key={i} className="border-t pt-3 text-sm"><p>{h.decision} · {h.actor} · {localDate(h.created_at)}</p><p>{h.notes}</p>{h.self_approval_override && <p className="text-amber-900">Explicit administrative self-approval exception</p>}</div>)}</CardContent></Card></div>
    <aside className="space-y-5"><Card><CardContent className="space-y-3 p-5"><h2 className="font-semibold">Submission details</h2><p className="text-sm">{draft.language} · {entry.format} · Revision {entry.version}</p><p className="text-sm">{entry.destinations.map(p => platforms[p]).join(", ")}</p><p className="text-sm">Requested: {localDate(entry.scheduled_at)}</p><p className="text-xs">Submitted: {localDate(entry.created_at)}</p><p className="text-sm">Default social caption: {draft.social_caption || "None"}</p>{Object.entries(draft.social_captions ?? {}).map(([channel, caption]) => <p key={channel} className="whitespace-pre-wrap text-sm">{channel} caption: {caption}</p>)}<p className="text-sm">Reviewer: {entry.reviewer ?? "Not yet assigned"}</p><p className="text-xs">Decision: {localDate(entry.decided_at)}</p>{entry.review_notes && <p className="rounded bg-muted p-3 text-sm">{entry.review_notes}</p>}<p className="whitespace-pre-wrap text-sm">Reporting notes: {draft.reporting_notes || "None"}</p>{draft.warnings.map(w => <p key={w} className="text-sm text-amber-900">⚠ {w} (non-blocking)</p>)}</CardContent></Card>
    {reviewer && ["IN_REVIEW", "APPROVED"].includes(entry.status) && <Card><CardContent className="space-y-4 p-5"><Field label="Review notes"><textarea rows={5} maxLength={5000} className={fieldClass} value={notes} onChange={e => setNotes(e.target.value)} /></Field>{user?.role === "SUPERADMIN" && <label className="flex gap-2 text-xs"><input type="checkbox" checked={override} onChange={e => setOverride(e.target.checked)} />Explicit administrative self-approval exception (reason required)</label>}<div className="flex flex-wrap gap-2">{entry.status === "IN_REVIEW" ? <><Button disabled={busy} onClick={() => decide("approve")}>Approve revision</Button><Button variant="outline" disabled={busy} onClick={() => decide("request-changes")}>Request changes</Button><Button variant="outline" disabled={busy} onClick={() => decide("reject")}>Reject</Button></> : <Button disabled={busy} onClick={() => decide("ready")}>Authorize READY for delivery</Button>}</div></CardContent></Card>}
    {(["IN_REVIEW", "QUEUED", "SCHEDULED"].includes(entry.status) || reviewer && ["APPROVED", "READY"].includes(entry.status)) && <Button disabled={busy} variant="outline" onClick={() => { if (window.confirm("Withdraw this submission and return the story to draft?")) void decide("withdraw"); }}>Withdraw submission</Button>}
    <Button asChild variant="outline"><Link href={entry.origin_item_id ? `/news-feeds/drafts/${entry.story_id}` : `/manual-writing/${entry.story_id}`}>Open story editor</Link></Button></aside></div>
  </>;
}
