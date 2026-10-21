"use client";
import { useState } from "react";
import type { CollectionSettings, Source, SourceTest } from "@/features/feeds/api";
import { newsroom } from "@/features/feeds/api";
import { Field, Feedback, fieldClass } from "@/features/feeds/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
const initial = { publisher: "", url: "", feed_url: "", source_type: "rss", language: "bn", category: "", rights: "metadata_only", extraction_mode: "metadata", polling_interval: 15, active: false, notes: "", draft_language: "" };
export function SourceForm({ source, defaults, onSaved, onCancel }: { source?: Source; defaults?: CollectionSettings; onSaved: () => void; onCancel: () => void }) {
  const [providerConfig, setProviderConfig] = useState<Record<string, string>>(source?.provider_config ?? {});
  const [form, setForm] = useState(source ? { ...initial, ...source, feed_url: source.feed_url ?? "", draft_language: source.draft_language ?? "" } : { ...initial, polling_interval: defaults?.default_interval ?? initial.polling_interval });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SourceTest | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  function change<K extends keyof typeof initial>(key: K, value: typeof initial[K]) {
    setForm(previous => ({ ...previous, [key]: value }));
    if (["url", "feed_url", "source_type", "rights", "extraction_mode"].includes(key)) setResult(null);
  }
  function payload() { return { ...Object.fromEntries(Object.keys(initial).map(key => [key, (key === "feed_url" || key === "draft_language") ? form[key] || null : form[key as keyof typeof initial]])), provider_config: providerConfig }; }
  async function test() {
    setBusy("test"); setError(null);
    try {
      setResult(await newsroom<SourceTest>("sources/test", { method: "POST", body: { url: form.url, source_type: form.source_type, feed_url: form.feed_url || null, rights: form.rights, extraction_mode: form.extraction_mode, provider_config: providerConfig } }));
    } catch (error) { setError((error as Error).message); } finally { setBusy(null); }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy("save"); setError(null);
    try { await newsroom(source ? `sources/${source.id}` : "sources", { method: source ? "PATCH" : "POST", body: payload() }); onSaved(); }
    catch (error) { setError((error as Error).message); } finally { setBusy(null); }
  }
  return <Card className="mb-6"><CardHeader><CardTitle>{source ? "Edit source" : "Add a source"}</CardTitle></CardHeader><CardContent><form onSubmit={save} className="space-y-5">
    <Feedback error={error} />
    {["INSTAGRAM_ACCOUNT", "GDELT", "GOOGLE_NEWS"].includes(form.source_type) && <div className="space-y-3 rounded border p-4"><p className="text-sm">Verify source permissions before activating. Instagram requires official Meta Business Discovery access; manual post links remain available.</p><Field label={form.source_type === "INSTAGRAM_ACCOUNT" ? "Instagram username (without @)" : "Discovery query"}><input required className={fieldClass} value={providerConfig[form.source_type === "INSTAGRAM_ACCOUNT" ? "username" : "query"] ?? ""} onChange={e => setProviderConfig({ ...providerConfig, [form.source_type === "INSTAGRAM_ACCOUNT" ? "username" : "query"]: e.target.value })} /></Field>{form.source_type === "GOOGLE_NEWS" && <div className="grid gap-3 sm:grid-cols-3">{["hl", "gl", "ceid"].map(key => <Field key={key} label={key}><input className={fieldClass} placeholder={{ hl: "en-BD", gl: "BD", ceid: "BD:en" }[key]} value={providerConfig[key] ?? ""} onChange={e => setProviderConfig({ ...providerConfig, [key]: e.target.value })} /></Field>)}</div>}</div>}
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Field label="Publisher name"><input autoFocus required maxLength={200} className={fieldClass} value={form.publisher} onChange={e => change("publisher", e.target.value)} placeholder="Original publisher" /></Field>
      <Field label="Source type"><select className={fieldClass} value={form.source_type} onChange={e => change("source_type", e.target.value)}><option value="rss">RSS / Atom feed</option><option value="website">Website · discover feeds</option><option value="json_feed">JSON Feed</option><option value="api">Public API · supported feed formats</option><option value="manual">Manual reference</option><option value="INSTAGRAM_ACCOUNT">Instagram account · official API / manual links</option><option value="GDELT">GDELT discovery</option><option value="GOOGLE_NEWS">Google News RSS discovery</option></select></Field>
      <Field label="Source URL"><input type="url" required maxLength={2048} className={fieldClass} value={form.url} onChange={e => change("url", e.target.value)} placeholder="https://publisher.example/feed" /></Field>
      <Field label="Feed URL (optional)"><input type="url" maxLength={2048} className={fieldClass} value={form.feed_url} onChange={e => change("feed_url", e.target.value)} placeholder="Select a discovered feed or enter its URL" /></Field>
      <Field label="Collection frequency (minutes)"><input type="number" min={5} max={1440} required className={fieldClass} value={form.polling_interval} onChange={e => change("polling_interval", Number(e.target.value))} /></Field>
      <Field label="Feed language (metadata)"><select className={fieldClass} value={form.language} onChange={e => change("language", e.target.value)}><option value="bn">বাংলা · Bengali</option><option value="en">English</option></select></Field>
      <Field label="Draft language override"><select className={fieldClass} value={form.draft_language} onChange={e => change("draft_language", e.target.value)}><option value="">Global default</option><option value="bn">Bengali</option><option value="en">English</option></select></Field>
      <Field label="Default category"><input maxLength={100} className={fieldClass} value={form.category} onChange={e => change("category", e.target.value)} placeholder="Used when the feed has no category" /></Field>
      <Field label="Usage / rights"><select className={fieldClass} value={form.rights} onChange={e => change("rights", e.target.value)}><option value="metadata_only">Public feed metadata only</option><option value="unverified">Rights unverified</option><option value="licensed">Licensed</option><option value="owned">BNC-owned</option><option value="prohibited">Collection prohibited</option></select></Field>
      <Field label="Collection mode"><select className={fieldClass} value={form.extraction_mode} onChange={e => change("extraction_mode", e.target.value)}><option value="metadata">Feed metadata</option><option value="reference_only">Reference only · do not fetch</option></select></Field>
    </div>
    <Field label="Rights / owner notes"><textarea maxLength={4000} rows={2} className={fieldClass} value={form.notes ?? ""} onChange={e => change("notes", e.target.value)} /></Field>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={e => change("active", e.target.checked)} />Active source</label>
    <p className="text-xs leading-5 text-muted-foreground">Collection reads permitted feed metadata only. Manual references and prohibited sources are never fetched. Unsupported APIs need a dedicated adapter. Do not paste API keys into URLs.</p>
    <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" onClick={test} disabled={!!busy || !form.url}>{busy === "test" ? "Testing source…" : "Test Source"}</Button><Button type="submit" disabled={!!busy}>{busy === "save" ? "Saving…" : "Save source"}</Button><Button type="button" variant="ghost" onClick={onCancel} disabled={!!busy}>Cancel</Button></div>
    {result && <div role="status" className={`rounded-lg border p-4 ${result.supported ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}><p className="font-medium">{result.supported ? "Source test passed" : "Source needs attention"}</p><p className="mt-1 text-sm">{result.message}</p>{result.feeds.length > 0 && <div className="mt-3 space-y-2">{result.feeds.map(feed => <div key={feed.url} className="flex flex-wrap items-center justify-between gap-2 rounded border bg-card p-3"><div className="min-w-0"><p className="text-sm font-medium">{feed.title || "Discovered feed"}</p><p className="break-all text-xs text-muted-foreground">{feed.url}</p></div><Button type="button" size="sm" variant="outline" onClick={() => setForm(previous => ({ ...previous, feed_url: feed.url }))}>Use feed</Button></div>)}</div>}{result.sample?.map(item => <p key={item.url} className="mt-2 text-xs text-muted-foreground">Preview · {item.title}</p>)}</div>}
  </form></CardContent></Card>;
}
