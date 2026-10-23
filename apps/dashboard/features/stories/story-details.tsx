"use client";
import { useSession } from "../accounts/session";
import { useState } from "react";
import { Draft, newsroom } from "../feeds/api";
import { Field, fieldClass } from "../feeds/shared";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MediaLibrary } from "../media/media-library";

export const platforms = { wordpress: "WordPress", facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn", x: "X" };
export type Platform = keyof typeof platforms;
export type StoryDetails = {
  format: "article" | "news_bite"; contributors: string; cover_image_id: string | null;
  image_alt: string; image_caption: string; reporting_notes: string;
  destinations: Platform[]; social_caption: string; schedule: string;
};
export function detailsFrom(draft: Draft): StoryDetails {
  const scheduled = draft.scheduled_at ? new Date(draft.scheduled_at) : null;
  return {
    format: draft.format ?? "article", contributors: (draft.contributors ?? (draft.assigned_author ? [draft.assigned_author.name] : [])).join(", "),
    cover_image_id: draft.cover_image_id ?? null, image_alt: draft.image_alt ?? "", image_caption: draft.image_caption ?? "",
    reporting_notes: draft.reporting_notes ?? "", destinations: draft.destinations ?? [], social_caption: draft.social_caption ?? "",
    schedule: scheduled ? new Date(scheduled.getTime() + 6 * 60 * 60 * 1000).toISOString().slice(0, 16) : "",
  };
}
export function detailsPayload(details: StoryDetails) {
  const { schedule, contributors, ...rest } = details;
  return { ...rest, contributors: [...new Set(contributors.split(",").map(s => s.trim()).filter(Boolean))], scheduled_at: schedule ? new Date(`${schedule}:00+06:00`).toISOString() : null };
}
type Props = { value: StoryDetails; onChange: (value: StoryDetails) => void };
export function CoverImage({ value, onChange, onUploading }: Props & { onUploading: (busy: boolean) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [choosing, setChoosing] = useState(false);
  async function upload(file?: File) {
    if (!file) return;
    setError(null);
    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type) || file.size > 3 * 1024 * 1024) {
      setError("Choose a JPG, PNG, WebP or GIF up to 3 MB."); return;
    }
    setUploading(true); onUploading(true);
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve((reader.result as string).split(",")[1]);
        reader.onerror = () => reject(new Error("Image could not be read")); reader.readAsDataURL(file);
      });
      const result = await newsroom<{ id: string }>("media", { method: "POST", body: { data } });
      onChange({ ...value, cover_image_id: result.id });
    } catch (e) { setError((e as Error).message); }
    finally { setUploading(false); onUploading(false); }
  }
  return <Card><CardHeader><CardTitle>Cover image</CardTitle></CardHeader><CardContent className="space-y-4">
    {value.cover_image_id ? <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="max-h-96 w-full rounded-lg object-contain" src={`/api/newsroom/media/${value.cover_image_id}`} alt={value.image_alt} />
      <Button type="button" variant="outline" disabled={uploading} onClick={() => onChange({ ...value, cover_image_id: null })}>Remove image</Button>
    </> : <p className="text-sm text-muted-foreground">Add a cover image to your article or news bite.</p>}
    <Field validationKey="cover_image_id" label={uploading ? "Uploading image…" : "Upload / replace image"}><input type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={uploading} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} className={fieldClass} /></Field>
    <p className="text-xs text-muted-foreground">JPG, PNG, WebP or GIF · up to 3 MB. Uploads are stored in Media Library. Save the revision to attach the image.</p>
    <Button type="button" variant="outline" disabled={uploading} onClick={() => setChoosing(open => !open)}>{choosing ? "Close media library" : "Choose from media library"}</Button>
    {choosing && <MediaLibrary onUploading={busy => { setUploading(busy); onUploading(busy); }} onSelect={id => { onChange({ ...value, cover_image_id: id }); setChoosing(false); }} />}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <Field label="Image alt text"><input maxLength={1000} className={fieldClass} value={value.image_alt} onChange={e => onChange({ ...value, image_alt: e.target.value })} /></Field>
    <Field label="Image caption / credit"><input maxLength={2000} className={fieldClass} value={value.image_caption} onChange={e => onChange({ ...value, image_caption: e.target.value })} /></Field>
  </CardContent></Card>;
}
export function DistributionDetails({ value, onChange }: Props) {
  const { user } = useSession();
  return <Card><CardHeader><CardTitle>Format & publishing</CardTitle></CardHeader><CardContent className="space-y-5">
    <Field label="Format" validationKey="format"><select className={fieldClass} value={value.format} onChange={e => onChange({ ...value, format: e.target.value as StoryDetails["format"] })}><option value="article">Article</option><option value="news_bite">News bite</option></select></Field>
    <Field label="Authors / contributors (comma separated)" validationKey="contributors"><input maxLength={4000} className={fieldClass} value={value.contributors} onChange={e => onChange({ ...value, contributors: e.target.value })} placeholder="Sam, Nadia" /></Field>
    <Field label="Source / reporting notes"><textarea rows={4} maxLength={10000} className={fieldClass} value={value.reporting_notes} onChange={e => onChange({ ...value, reporting_notes: e.target.value })} /></Field>
    <Field group label="Publishing destinations" validationKey="destinations"><fieldset className="space-y-3"><legend className="mb-3 text-sm font-medium">Publishing destinations</legend>{(Object.entries(platforms) as [Platform, string][]).map(([key, label]) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.destinations.includes(key)} onChange={e => onChange({ ...value, destinations: e.target.checked ? [...value.destinations, key] : value.destinations.filter(p => p !== key) })} />{label}</label>)}</fieldset></Field>
    <Field label="Default social caption"><textarea rows={4} maxLength={5000} className={fieldClass} value={value.social_caption} onChange={e => onChange({ ...value, social_caption: e.target.value })} /></Field>
    <p className="text-xs leading-5 text-muted-foreground">Facebook and Instagram captions below override this default. WordPress uses the full story.</p>
    {user?.role !== "CONTENT_WRITER" && <Field validationKey="scheduled_at" label="Schedule · Dhaka time (UTC+06:00)"><input type="datetime-local" className={fieldClass} value={value.schedule} onChange={e => onChange({ ...value, schedule: e.target.value })} /></Field>}
    {value.schedule && <Button type="button" variant="ghost" onClick={() => onChange({ ...value, schedule: "" })}>Clear schedule</Button>}
    <p className="text-xs leading-5 text-muted-foreground">Leave the schedule empty for the immediate queue. Sending requires content, category, tags and contributors. Delivery awaits editorial approval and connected platform accounts.</p>
  </CardContent></Card>;
}
