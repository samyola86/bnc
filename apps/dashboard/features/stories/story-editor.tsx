"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StoryPreview } from "./story-preview";
import { AIDraftPanel, AppliedAI } from "./ai-draft-panel";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/layout/page-header";
import { Credit, Draft, localDate, newsroom } from "../feeds/api";
import { Feedback, Field, fieldClass } from "../feeds/shared";
import { useRemote } from "../feeds/use-remote";
import { CoverImage, DistributionDetails, detailsFrom, detailsPayload } from "./story-details";

export function StoryEditor({ id, manual = false }: { id: string; manual?: boolean }) {
  const { data, error, refresh } = useRemote<Draft>(`stories/${id}`);
  return <><PageHeader title={manual ? "Manual story" : "Candidate draft"} description="Write and preview original reporting with saved revisions and source credits." action={<Button asChild variant="outline"><Link href={manual ? "/manual-writing" : "/news-feeds"}><ArrowLeft />{manual ? "Back to manual stories" : "Back to candidates"}</Link></Button>} /><Feedback error={error} />{data ? <DraftForm key={`${data.id}-${data.version}`} draft={data} onSaved={refresh} /> : !error && <p className="text-sm text-muted-foreground">Loading draft…</p>}</>;
}

function DraftForm({ draft, onSaved }: { draft: Draft; onSaved: () => void }) {
  const router = useRouter();
  const [details, setDetails] = useState(() => detailsFrom(draft));
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [title, setTitle] = useState(draft.title);
  const [summary, setSummary] = useState(draft.summary);
  const [body, setBody] = useState(draft.body);
  const [category, setCategory] = useState(draft.category);
  const [language, setLanguage] = useState(draft.language);
  const [tags, setTags] = useState((draft.tags ?? []).join(", "));
  const [captions, setCaptions] = useState(draft.social_captions ?? {});
  const [aiJobId, setAiJobId] = useState<string | null>(null);
  const [aiWarnings, setAiWarnings] = useState([...(draft.editorial_warnings ?? []), ...(draft.claims_to_verify ?? [])]);
  const [credits, setCredits] = useState(draft.credits);
  const [version, setVersion] = useState(draft.version);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(details) !== JSON.stringify(detailsFrom(draft)) || title !== draft.title || summary !== draft.summary || body !== draft.body || category !== draft.category || language !== draft.language || tags !== (draft.tags ?? []).join(", ") || JSON.stringify(captions) !== JSON.stringify(draft.social_captions ?? {}) || JSON.stringify(credits) !== JSON.stringify(draft.credits);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  function applyAI(preview: AppliedAI) {
    setTitle(preview.title); setSummary(preview.summary); setBody(preview.body); setCategory(preview.category);
    setLanguage(preview.language); setTags(preview.tags.join(", ")); setCaptions(preview.social_captions);
    setAiJobId(preview.ai_job_id); setAiWarnings([...preview.editorial_warnings, ...preview.claims_to_verify]);
    setNotice("AI preview applied to the editor. Verify and edit the writing, then save revision.");
  }
  const missing = !credits.some(c => c.is_original_reporting || c.publisher_name.trim() || c.attribution_text.trim());
  const incomplete = credits.some(c => !c.is_original_reporting && !c.publisher_name.trim() && !c.attribution_text.trim());
  function changeCredit(index: number, update: Partial<Credit>) { setCredits(previous => previous.map((credit, i) => i === index ? { ...credit, ...update } : credit)); }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (uploading) return; const queue = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "queue"; setBusy(true); setError(null); setNotice(null);
    try {
      const updated = await newsroom<Draft>(`stories/${draft.id}`, { method: "PATCH", body: {
        ...detailsPayload(details), base_version: version, title, summary, body, category, language, tags: tags.split(",").map(tag => tag.trim()).filter(Boolean), social_captions: captions, ai_job_id: aiJobId,
        credits: credits.map(({ source_id, publisher_name, original_url, attribution_text, is_original_reporting, rights_status }) => ({ source_id, publisher_name, original_url: original_url || null, attribution_text, is_original_reporting, rights_status })),
      } });
      setVersion(updated.version); setAiJobId(null);
      if (queue) { await newsroom(`stories/${draft.id}/queue`, { method: "POST", body: { base_version: updated.version } }); router.push("/publishing"); return; }
      setNotice(`Saved revision ${updated.version}${updated.warnings.length ? ` · ${updated.warnings.join(", ")}` : ""}`); onSaved();
    } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
  }
  return <form onSubmit={save}><Feedback error={error} message={notice} />
    {aiWarnings.length > 0 && <div role="status" className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><p className="font-semibold">AI-assisted writing · human review required</p><ul className="mt-2 list-disc pl-5">{aiWarnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></div>}
    {(missing || incomplete) && <div role="status" className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><p className="font-semibold">{missing ? "Missing source credit" : "Attribution needs review"}</p><p className="mt-1">Add or edit Sources & Credits below. This warning does not block saving or publishing; rights and editorial approval remain separate requirements.</p></div>}
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted-foreground">{draft.status} · Revision {version}{dirty ? " · Unsaved changes" : " · Saved"} · Save creates a new immutable revision.</p><div className="flex gap-2"><Button type="button" variant="outline" onClick={() => setPreviewing(value => !value)}>{previewing ? "Back to writing" : "Preview story"}</Button><Button type="button" variant="outline" onClick={() => { if (!dirty || window.confirm("Discard unsaved changes and reload the saved revision?")) window.location.reload(); }} disabled={busy}>Reload saved draft</Button><Button type="submit" disabled={busy || uploading || !title.trim()}><Save />{busy ? "Saving…" : "Save revision"}</Button></div></div>
    <fieldset disabled={busy || uploading}><div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]"><div className="space-y-6">{previewing ? <StoryPreview title={title} summary={summary} body={body} category={category} tags={tags.split(",").map(t => t.trim()).filter(Boolean)} language={language} credits={credits} details={details} /> : <Card><CardContent className="space-y-5 p-6"><Field label="Headline"><input required maxLength={500} className={`${fieldClass} text-lg font-semibold`} value={title} onChange={e => setTitle(e.target.value)} /></Field><Field label="Summary"><textarea rows={3} maxLength={5000} className={fieldClass} value={summary} onChange={e => setSummary(e.target.value)} /></Field><CoverImage value={details} onChange={setDetails} onUploading={setUploading} /><Field label="Story body"><textarea rows={18} maxLength={100000} className={`${fieldClass} leading-7`} value={body} onChange={e => setBody(e.target.value)} placeholder="Write original BNC reporting here. The full publisher article is not imported." /></Field></CardContent></Card>}

      <AIDraftPanel id={draft.id} version={version} language={language} onApply={applyAI} />
      <Card><CardHeader><CardTitle>Sources & Credits</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm leading-6 text-muted-foreground">Feed credits are prepopulated. Add a manual publisher, a credit note, or original BNC reporting. A URL is optional; no link is invented when it is absent.</p>{credits.map((credit, index) => <div key={index} className="space-y-3 rounded-lg border p-4"><div className="flex items-center justify-between"><p className="text-sm font-semibold">Source credit {index + 1}</p><Button type="button" variant="ghost" size="sm" aria-label={`Remove source credit ${index + 1}`} onClick={() => setCredits(previous => previous.filter((_, i) => i !== index))}><Trash2 /></Button></div><div className="grid gap-3 md:grid-cols-2"><Field label="Publisher name"><input maxLength={200} className={fieldClass} value={credit.publisher_name} onChange={e => changeCredit(index, { publisher_name: e.target.value })} /></Field><Field label="Original URL (optional)"><input type="url" maxLength={2048} className={fieldClass} value={credit.original_url ?? ""} onChange={e => changeCredit(index, { original_url: e.target.value })} /></Field></div><Field label="Attribution / credit note"><textarea maxLength={2000} rows={2} className={fieldClass} value={credit.attribution_text} onChange={e => changeCredit(index, { attribution_text: e.target.value })} /></Field><Field label="Rights status"><select className={fieldClass} value={credit.rights_status} onChange={e => changeCredit(index, { rights_status: e.target.value })}><option value="unverified">Unverified</option><option value="metadata_only">Metadata only</option><option value="licensed">Licensed</option><option value="owned">BNC-owned</option><option value="prohibited">Prohibited</option></select></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={credit.is_original_reporting} onChange={e => changeCredit(index, { is_original_reporting: e.target.checked })} />Original BNC reporting</label></div>)}<Button type="button" variant="outline" disabled={credits.length >= 30} onClick={() => setCredits(previous => [...previous, { source_id: null, publisher_name: "", original_url: null, attribution_text: "", is_original_reporting: false, rights_status: "unverified" }])}><Plus />Add Source</Button></CardContent></Card>
    </div><aside className="space-y-6"><DistributionDetails value={details} onChange={setDetails} /><Card><CardHeader><CardTitle>Story details</CardTitle></CardHeader><CardContent className="space-y-5"><Field label="Language"><select className={fieldClass} value={language} onChange={e => setLanguage(e.target.value as "bn" | "en")}><option value="bn">বাংলা · Bengali</option><option value="en">English</option></select></Field><Field label="Category"><input maxLength={100} className={fieldClass} value={category} onChange={e => setCategory(e.target.value)} /></Field><Field label="Tags (comma separated)"><input className={fieldClass} value={tags} onChange={e => setTags(e.target.value)} /></Field>{(["facebook", "instagram"] as const).map(channel => <Field key={channel} label={`${channel} caption`}><textarea rows={3} maxLength={5000} className={fieldClass} value={captions[channel] ?? ""} onChange={e => setCaptions({ ...captions, [channel]: e.target.value })} /></Field>)}<Field label="Assigned author"><p className="text-sm text-muted-foreground">{draft.assigned_author?.name ?? "Unassigned"}</p></Field><p className="text-xs leading-5 text-muted-foreground">All writing, tags, language and captions remain editable. AI suggestions require human review.</p></CardContent></Card><Card><CardHeader><CardTitle>Original feed provenance</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-xs leading-5 text-muted-foreground">These ingestion records remain available even when you edit or remove a visible credit.</p>{!draft.provenance.length && <p className="text-xs text-muted-foreground">Independently authored story. Add any supporting sources in Sources & Credits.</p>}{draft.provenance.map((credit, index) => <div key={`${credit.source_id}-${index}`} className="border-t pt-4 text-xs leading-5"><p className="font-semibold">{credit.publisher_name}</p><a href={credit.original_url} target="_blank" rel="noreferrer" className="break-all text-primary underline">{credit.original_url}</a><p className="mt-2">Published: {localDate(credit.published_at)}<br />Retrieved: {localDate(credit.retrieved_at)}<br />Rights: {credit.rights_status.replaceAll("_", " ")}</p></div>)}</CardContent></Card></aside></div></fieldset>
    <div className="sticky bottom-0 z-10 mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card/95 p-4 shadow-sm backdrop-blur"><p role="status" className="text-xs text-muted-foreground">Revision {version} · {dirty ? "Unsaved changes" : "Saved"} · Human review precedes publication</p><div className="flex gap-2"><Button type="button" variant="outline" onClick={() => setPreviewing(value => !value)}>{previewing ? "Back to writing" : "Preview"}</Button><Button type="submit" disabled={busy || uploading || !title.trim()}><Save />{busy ? "Saving…" : "Save revision"}</Button><Button type="submit" name="action" value="queue" disabled={busy || uploading || !title.trim()}>Send to publishing →</Button></div></div>
  </form>;
}
