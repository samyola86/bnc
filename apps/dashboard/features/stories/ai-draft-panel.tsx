"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { newsroom } from "@/features/feeds/api";
import { Feedback, Field, fieldClass } from "@/features/feeds/shared";

type Result = { language: "bn" | "en"; headline: string; summary: string; paragraphs: { text: string; supporting_source_ids: string[] }[]; category: string; tags: string[]; social_captions: { facebook: string; instagram: string }; claims_to_verify: string[]; editorial_warnings: string[] };
type Job = { id: string; base_version: number; status: string; message: string; result: Result | null };
export type AppliedAI = { title: string; summary: string; body: string; category: string; language: "bn" | "en"; tags: string[]; social_captions: { facebook: string; instagram: string }; ai_job_id: string; claims_to_verify: string[]; editorial_warnings: string[] };

export function AIDraftPanel({ id, version, language, onApply }: { id: string; version: number; language: "bn" | "en"; onApply: (draft: AppliedAI) => void }) {
  const [notes, setNotes] = useState("");
  const [permitted, setPermitted] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollAttempt, setPollAttempt] = useState(0);
  const running = job?.status === "PENDING" || job?.status === "RUNNING";
  const jobId = job?.id;
  useEffect(() => {
    let active = true;
    newsroom<{ items: Job[] }>(`stories/${id}/ai-jobs`).then(data => { if (active) setJob(data.items[0] ?? null); }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [id]);
  useEffect(() => {
    if (!running || !jobId) return;
    let active = true;
    const poll = async () => {
      try { const updated = await newsroom<Job>(`ai/jobs/${jobId}`); if (active) { setJob(updated); setError(null); } }
      catch (error) { if (active) setError((error as Error).message); }
    };
    const timer = setInterval(() => void poll(), 2000);
    void poll();
    return () => { active = false; clearInterval(timer); };
  }, [running, jobId, pollAttempt]);
  async function generate() {
    setRequesting(true); setError(null);
    try {
      const accepted = await newsroom<{ job_id: string }>(`stories/${id}/ai-draft`, { method: "POST", body: { base_version: version, language, reporting_notes: notes, notes_permitted: permitted } });
      setJob({ id: accepted.job_id, base_version: version, status: "PENDING", message: "Queued for AI drafting", result: null });
    } catch (error) { setError((error as Error).message); } finally { setRequesting(false); }
  }
  return <Card><CardHeader><CardTitle>AI News Generator</CardTitle></CardHeader><CardContent className="space-y-4">
    <p className="text-sm leading-6 text-muted-foreground">Generate in the selected story language from permitted RSS metadata and/or the factual notes below. No article pages are fetched. A URL alone provides no evidence. Saved writing stays intact until you apply and save the preview.</p>
    <Field label="Reporting notes / permitted evidence"><textarea maxLength={15000} rows={4} className={fieldClass} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Supply facts, context and attribution you are permitted to use. For manual stories this is required; existing writing is not sent automatically." /></Field>
    <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={permitted} onChange={e => setPermitted(e.target.checked)} />I am permitted to send these notes to OpenAI for drafting.</label>
    <Feedback error={error} />
    <div className="flex flex-wrap items-center gap-3"><Button type="button" variant="outline" disabled={requesting || running || (!!notes.trim() && !permitted)} onClick={generate}><Sparkles />{requesting || running ? "Generating…" : "Generate with AI"}</Button>{job && <p role="status" className="text-sm text-muted-foreground">{job.message}</p>}{error && running && <Button type="button" variant="ghost" onClick={() => setPollAttempt(value => value + 1)}>Retry status</Button>}</div>
    {job?.status === "FAILED" && <Feedback error={job.message} />}
    {job?.result && <AIPreview key={job.id} job={job as Job & { result: Result }} stale={job.base_version !== version} onApply={onApply} />}
  </CardContent></Card>;
}

function AIPreview({ job, stale, onApply }: { job: Job & { result: Result }; stale: boolean; onApply: (draft: AppliedAI) => void }) {
  const [preview, setPreview] = useState<AppliedAI>({ title: job.result.headline, summary: job.result.summary, body: job.result.paragraphs.map(p => p.text).join("\n\n"), category: job.result.category, tags: job.result.tags, language: job.result.language, social_captions: job.result.social_captions, ai_job_id: job.id, claims_to_verify: job.result.claims_to_verify, editorial_warnings: job.result.editorial_warnings });
  return <div className="space-y-4 rounded-lg border border-amber-200 bg-amber-50/40 p-4">
    <h3 className="font-semibold">Editable AI preview · human review required</h3>
    <p className="text-sm text-amber-900">AI output may contain errors. Verify every fact, quotation and source. Applying replaces the writing fields in this editor; Sources & Credits stay under your control. Save revision commits your edited preview.</p>
    {stale && <p role="alert" className="text-sm text-destructive">The saved revision changed. Generate again before applying this preview.</p>}
    <Field label="AI headline"><input className={fieldClass} maxLength={500} value={preview.title} onChange={e => setPreview({ ...preview, title: e.target.value })} /></Field>
    <Field label="AI summary"><textarea className={fieldClass} rows={3} maxLength={5000} value={preview.summary} onChange={e => setPreview({ ...preview, summary: e.target.value })} /></Field>
    <Field label="AI body"><textarea className={`${fieldClass} leading-7`} rows={12} maxLength={100000} value={preview.body} onChange={e => setPreview({ ...preview, body: e.target.value })} /></Field>
    <Field label="Suggested category"><input className={fieldClass} maxLength={100} value={preview.category} onChange={e => setPreview({ ...preview, category: e.target.value })} /></Field>
    <Field label="Suggested tags (comma separated)"><input className={fieldClass} value={preview.tags.join(", ")} onChange={e => setPreview({ ...preview, tags: e.target.value.split(",").map(t => t.trim()) })} /></Field>
    {(["facebook", "instagram"] as const).map(channel => <Field key={channel} label={`AI ${channel} caption`}><textarea rows={3} maxLength={5000} className={fieldClass} value={preview.social_captions[channel]} onChange={e => setPreview({ ...preview, social_captions: { ...preview.social_captions, [channel]: e.target.value } })} /></Field>)}
    <div className="text-sm"><p className="font-medium">Verification and evidence</p><ul className="mt-2 list-disc space-y-1 pl-5">{[...preview.editorial_warnings, ...preview.claims_to_verify].map((warning, i) => <li key={i}>{warning}</li>)}</ul>{job.result.paragraphs.map((p, i) => <p key={i} className="mt-2 break-all text-xs text-muted-foreground">Paragraph {i + 1} evidence: {p.supporting_source_ids.join(", ")}</p>)}</div>
    <Button type="button" disabled={stale || !preview.title.trim()} onClick={() => { if (window.confirm("Replace the current headline, summary, body, category, tags, language and captions with this AI preview? Any unsaved writing in those fields will be replaced. Credits are preserved. You must still save the revision.")) onApply(preview); }}>Apply preview to editor</Button>
  </div>;
}
