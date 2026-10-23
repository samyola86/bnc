"use client";
/* eslint-disable @next/next/no-img-element -- Private authenticated media URLs. */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { newsroom } from "../feeds/api";
import { Feedback } from "../feeds/shared";

type Asset = { id: string; size: number; uploaded_at: string };
type MediaPage = { items: Asset[]; next_cursor: string | null };

export function MediaLibrary({ onSelect, onUploading }: { onSelect?: (id: string) => void; onUploading?: (busy: boolean) => void }) {
  const [data, setData] = useState<MediaPage | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    newsroom<MediaPage>(`media${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`)
      .then(page => { if (active) setData(page); })
      .catch(e => { if (active) setError((e as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [cursor, generation]);
  function refresh(next: string | null = null) {
    setLoading(true); setError(null); setData(null); setCursor(next); setGeneration(n => n + 1);
  }
  async function upload(file?: File) {
    if (!file) return;
    setError(null);
    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type) || file.size > 3 * 1024 * 1024) {
      setError("Choose a JPG, PNG, WebP or GIF up to 3 MB."); return;
    }
    setUploading(true); onUploading?.(true);
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve((reader.result as string).split(",")[1]);
        reader.onerror = () => reject(new Error("Image could not be read"));
        reader.readAsDataURL(file);
      });
      const asset = await newsroom<{ id: string }>("media", { method: "POST", body: { data } });
      refresh();
      if (onSelect) onSelect(asset.id);
    } catch (e) { setError((e as Error).message); }
    finally { setUploading(false); onUploading?.(false); }
  }
  return <section aria-label="Media library" className="space-y-4">
    <p className="text-sm text-muted-foreground">Images uploaded here or in the story editor are saved in this shared newsroom library. Saved News Bite graphics also appear here.</p>
    <div className="flex flex-wrap items-center gap-3"><label className="text-sm font-medium">Upload to media library<input aria-label="Upload to media library" type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={uploading} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} className="mt-2 block" /></label><Button type="button" variant="outline" disabled={loading || uploading} onClick={() => refresh()}>Refresh library</Button></div>
    <p className="text-xs text-muted-foreground">JPG, PNG, WebP or GIF · up to 3 MB. Removing an image from a story keeps it in the library.</p>
    <Feedback error={error} />
    {(loading || uploading) && <p role="status">{uploading ? "Uploading image…" : "Loading media…"}</p>}
    {!loading && data?.items.length === 0 && <p>No images yet. Upload an image to get started.</p>}
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">{data?.items.map(asset => <article key={asset.id} className="space-y-3 rounded-lg border bg-card p-3">
      <img src={`/api/newsroom/media/${asset.id}`} alt={`Library image ${asset.id}`} loading="lazy" className="aspect-square w-full rounded object-contain bg-muted" />
      <p className="break-all text-xs text-muted-foreground">{asset.id}<br />{Math.ceil(asset.size / 1024)} KB · {new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", dateStyle: "medium" }).format(new Date(asset.uploaded_at))}</p>
      {onSelect ? <Button type="button" disabled={uploading} onClick={() => onSelect(asset.id)}>Use image</Button> : <a href={`/api/newsroom/media/${asset.id}`} target="_blank" rel="noreferrer" className="text-sm text-primary underline">View image</a>}
    </article>)}</div>
    <div className="flex gap-3">{cursor && <Button type="button" variant="outline" disabled={loading || uploading} onClick={() => refresh()}>First page</Button>}{data?.next_cursor && <Button type="button" variant="outline" disabled={loading || uploading} onClick={() => refresh(data.next_cursor)}>Next page</Button>}</div>
  </section>;
}
