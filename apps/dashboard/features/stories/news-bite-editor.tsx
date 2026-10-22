"use client";
/* eslint-disable @next/next/no-img-element -- The renderer supplies exact private PNG bytes. */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Feedback, fieldClass } from "../feeds/shared";
import { newsroom } from "../feeds/api";
import { CoverImage, type StoryDetails } from "./story-details";

export type NewsBite = {
  template_id: "newspaper" | "dark-editorial" | "breaking-news" | "modern-magazine";
  template_version: 1; layout_version: 1; headline: string; highlight: string; supporting: string;
  speaker: string; source_credit: string; publication_date: string | null;
  focal_x: number; focal_y: number; image_rights: "unverified" | "owned" | "licensed" | "prohibited"; footer: string;
};
export const templates = [
  ["newspaper", "BNC Newspaper", "01"], ["dark-editorial", "BNC Dark Editorial", "02"],
  ["breaking-news", "BNC Breaking News", "03"], ["modern-magazine", "BNC Modern Magazine", "04"],
] as const;
export function initialNewsBite(headline: string, supporting: string): NewsBite {
  return { template_id: "newspaper", template_version: 1, layout_version: 1, headline, supporting,
    highlight: "", speaker: "", source_credit: "", publication_date: new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()),
    focal_x: .5, focal_y: .5, image_rights: "unverified", footer: "Trusted News. A Stronger Bangladesh." };
}
type Render = { png: string; errors: string[]; warnings: string[]; width: number; height: number };
type Props = { id: string; value: NewsBite; onChange: (value: NewsBite) => void; details: StoryDetails;
  onDetails: (details: StoryDetails) => void; category: string; onCategory: (value: string) => void;
  onUploading: (value: boolean) => void; onValidity: (valid: boolean) => void; publishing: React.ReactNode };

export function NewsBiteEditor({ id, value, onChange, details, onDetails, category, onCategory, onUploading, onValidity, publishing }: Props) {
  const [rendered, setRendered] = useState<{ key: string; result: Render } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enlarged, setEnlarged] = useState(false);
  const key = JSON.stringify({ news_bite: value, cover_image_id: details.cover_image_id, category, image_caption: details.image_caption });
  const current = rendered?.key === key ? rendered.result : null;
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    onValidity(false);
    const timer = setTimeout(() => {
      setError(null);
      newsroom<Render>(`stories/${id}/news-bite/preview`, { method: "POST", body: JSON.parse(key), signal: controller.signal })
        .then(result => { if (active) { setRendered({ key, result }); onValidity(!result.errors.length); } })
        .catch(e => { if (active) setError(Object.values((e as { fields?: Record<string, string> }).fields ?? {}).join(" ") || (e as Error).message); });
    }, 250);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [id, key, onValidity]);
  const change = <K extends keyof NewsBite>(field: K, next: NewsBite[K]) => onChange({ ...value, [field]: next });
  const src = current ? `data:image/png;base64,${current.png}` : undefined;
  return <section aria-label="News Bite template editor" className="grid items-start gap-6 lg:grid-cols-2">
    <div className="space-y-5"><Card><CardHeader><CardTitle>News Bite design</CardTitle></CardHeader><CardContent className="space-y-5">
      <Field label="Template" validationKey="news_bite" group><div className="grid grid-cols-2 gap-3">{templates.map(([id, name, number]) => <button type="button" key={id} aria-pressed={value.template_id === id} onClick={() => change("template_id", id)} className={`rounded-lg border-2 p-2 text-left text-xs font-semibold ${value.template_id === id ? "border-primary bg-primary/5" : "border-border"}`}><img className="mb-2 aspect-[4/5] w-full rounded object-cover" src={`/templates/thumbnails/${id}.png`} alt={`${name} template thumbnail`} />{number} · {name}</button>)}</div></Field>
      <Field label="Graphic headline" validationKey="news_bite_headline"><textarea rows={4} maxLength={1500} className={fieldClass} value={value.headline} onChange={e => change("headline", e.target.value)} /></Field>
      <Field label="Highlighted headline segment"><textarea rows={2} maxLength={1500} className={fieldClass} value={value.highlight} onChange={e => change("highlight", e.target.value)} /></Field>
      <p className="text-xs text-muted-foreground">Paste the exact text to emphasize. The first matching segment is colored; text is never duplicated.</p>
      <Field label="Supporting description"><textarea rows={4} maxLength={5000} className={fieldClass} value={value.supporting} onChange={e => change("supporting", e.target.value)} /></Field>
      <Field label="Speaker attribution"><input maxLength={250} className={fieldClass} value={value.speaker} onChange={e => change("speaker", e.target.value)} /></Field>
      <Field label="Original source credit"><input maxLength={300} className={fieldClass} value={value.source_credit} onChange={e => change("source_credit", e.target.value)} /></Field>
      <Field label="Graphic publication date"><input type="date" className={fieldClass} value={value.publication_date ?? ""} onChange={e => change("publication_date", e.target.value || null)} /></Field>
      <Field label="Graphic category"><input maxLength={100} className={fieldClass} value={category} onChange={e => onCategory(e.target.value)} /></Field>
      <Field label="Graphic footer"><input maxLength={150} className={fieldClass} value={value.footer} onChange={e => change("footer", e.target.value)} /></Field>
    </CardContent></Card>
    <CoverImage value={details} onChange={onDetails} onUploading={onUploading} />
    <Card><CardContent className="space-y-4 p-5">
      <Field label="Photograph usage rights" validationKey="news_bite_rights"><select className={fieldClass} value={value.image_rights} onChange={e => change("image_rights", e.target.value as NewsBite["image_rights"])}><option value="unverified">Unverified</option><option value="owned">BNC-owned</option><option value="licensed">Licensed for this use</option><option value="prohibited">Prohibited</option></select></Field>
      {(["x", "y"] as const).map(axis => <Field key={axis} label={`Photo focal point ${axis === "x" ? "horizontal" : "vertical"}`}><input type="range" min="0" max="1" step="0.01" className={fieldClass} value={value[`focal_${axis}`]} onChange={e => change(`focal_${axis}`, Number(e.target.value))} /></Field>)}
      <p className="text-xs text-muted-foreground">Adjust the crop without changing your original image. Only upload photographs you have permission to use.</p>
    </CardContent></Card>{publishing}</div>
    <aside className="space-y-4 lg:sticky lg:top-6" data-field="news_bite_render"><Card><CardHeader><CardTitle>Live graphic · 1080 × 1350</CardTitle></CardHeader><CardContent className="space-y-4">
      <Feedback error={error} />
      {!current && <p role="status" className="text-sm">Updating preview…</p>}
      {current?.errors.map(message => <p role="alert" key={message} className="rounded bg-red-50 p-3 text-sm text-red-900">{message}</p>)}
      {current?.warnings.map(message => <p role="status" key={message} className="rounded bg-amber-50 p-3 text-sm text-amber-900">{message}</p>)}
      {src && <img src={src} alt="Live News Bite graphic" width={1080} height={1350} className="aspect-[4/5] w-full rounded shadow-lg" />}
      <div className="flex flex-wrap gap-3"><Button type="button" variant="outline" disabled={!current || !!current.errors.length} onClick={() => setEnlarged(true)}>Enlarge preview</Button>{src && !current?.errors.length && details.cover_image_id && <Button asChild><a download={`bnc-${value.template_id}.png`} href={src}>Export PNG</a></Button>}</div>
      <p className="text-xs text-muted-foreground">Your PNG download matches this preview. Save revision to attach the graphic for editorial review. Exporting does not save or publish.</p>
    </CardContent></Card></aside>
    {enlarged && src && <div role="dialog" aria-modal="true" aria-label="Enlarged News Bite preview" onKeyDown={e => { if (e.key === "Escape") setEnlarged(false); if (e.key === "Tab") e.preventDefault(); }} className="fixed inset-0 z-50 overflow-auto bg-black/90 p-5"><Button type="button" autoFocus onClick={() => setEnlarged(false)} className="sticky top-0">Close enlarged preview</Button><img src={src} alt="Enlarged News Bite graphic" width={1080} height={1350} className="mx-auto h-auto max-w-full" /></div>}
  </section>;
}
