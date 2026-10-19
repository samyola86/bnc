"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CollectionSettings, newsroom } from "@/features/feeds/api";
import { Feedback, Field, fieldClass } from "@/features/feeds/shared";

export function AutomaticCollection({ settings, onSaved }: { settings: CollectionSettings; onSaved: () => void }) {
  const [form, setForm] = useState(settings);
  const [categories, setCategories] = useState(settings.preferred_categories.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setNotice(null);
    try {
      await newsroom<CollectionSettings>("ingestion/settings", { method: "PATCH", body: { ...form, preferred_categories: categories.split(",").map(c => c.trim()).filter(Boolean) } });
      setNotice("Collection settings saved in the newsroom database."); onSaved();
    } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
  }
  return <Card className="mb-6 border-primary/20"><CardHeader><CardTitle>Automatic Story Collection</CardTitle></CardHeader><CardContent><form onSubmit={save} className="space-y-5">
    <Feedback error={error} message={notice} />
    <fieldset disabled={busy} className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <Field label="Stories per batch (20–50)"><input className={fieldClass} type="number" min={20} max={50} required value={form.candidate_limit} onChange={e => setForm({ ...form, candidate_limit: Number(e.target.value) })} /></Field>
      <Field label="Default collection frequency (minutes)"><input className={fieldClass} type="number" min={5} max={1440} required value={form.default_interval} onChange={e => setForm({ ...form, default_interval: Number(e.target.value) })} /></Field>
      <Field label="Preferred draft language"><select className={fieldClass} value={form.draft_language} onChange={e => setForm({ ...form, draft_language: e.target.value as "bn" | "en" })}><option value="bn">বাংলা · Bengali</option><option value="en">English</option></select></Field>
      <Field label="Scheduled source collection mode"><select className={fieldClass} value={form.source_mode} onChange={e => setForm({ ...form, source_mode: e.target.value as CollectionSettings["source_mode"] })}><option value="all_supported">All supported feeds + discovery / feed APIs</option><option value="feeds_only">Direct RSS / Atom / JSON Feed only</option></select></Field>
    </fieldset>
    <Field label="Preferred news categories (comma separated)"><input maxLength={2000} className={fieldClass} value={categories} onChange={e => setCategories(e.target.value)} placeholder="Business, Technology, Bangladesh" /></Field>
    <div className="flex flex-wrap items-center justify-between gap-4"><label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={form.automatic_collection} disabled={busy} onChange={e => setForm({ ...form, automatic_collection: e.target.checked })} />Enable automatic collection</label><Button disabled={busy}>{busy ? "Saving…" : "Save collection settings"}</Button></div>
    <div className="space-y-1 text-xs leading-5 text-muted-foreground"><p>Batch size limits the queue display, never ingestion. Frequency applies to newly added sources; existing per-source intervals and backoff stay in force. Draft language applies to new stories and their AI editor, with per-source and per-story overrides.</p><p>Preferred categories are an optional Incoming Stories filter. Feed categories are preserved. Pausing automatic collection or limiting scheduled source types still allows explicit Collect now for permitted sources.</p><p>Website support discovers advertised feeds only. Public APIs must return RSS, Atom or JSON Feed. Full website extraction and custom API adapters are unavailable. Collection never automatically generates AI drafts or publishes.</p></div>
  </form></CardContent></Card>;
}
