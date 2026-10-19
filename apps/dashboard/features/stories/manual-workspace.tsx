"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Draft, localDate, newsroom } from "@/features/feeds/api";
import { Feedback, Field, fieldClass } from "@/features/feeds/shared";
import { useRemote } from "@/features/feeds/use-remote";

type StoryPage = { items: (Draft & { updated_at: string })[]; total: number; next_cursor: string | null };

export function ManualWorkspace() {
  const router = useRouter();
  const [cursor, setCursor] = useState<string | null>(null);
  const { data, error, refresh } = useRemote<StoryPage>(`stories?origin=manual${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("bn");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setFailure(null);
    try {
      const draft = await newsroom<Draft>("stories", { method: "POST", body: { title, language } });
      router.push(`/manual-writing/${draft.id}`);
    } catch (error) { setFailure((error as Error).message); setBusy(false); }
  }
  return <div className="space-y-6">
    <Feedback error={error ?? failure} />
    <Card><CardContent className="p-6"><form onSubmit={create} className="flex flex-wrap items-end gap-4">
      <div className="min-w-64 flex-1"><Field label="New story headline"><input required maxLength={500} className={fieldClass} value={title} onChange={e => setTitle(e.target.value)} placeholder="Start an independently authored story" /></Field></div>
      <Field label="Language"><select className={fieldClass} value={language} onChange={e => setLanguage(e.target.value)}><option value="bn">বাংলা · Bengali</option><option value="en">English</option></select></Field>
      <Button disabled={busy || !title.trim()}><Plus />{busy ? "Creating…" : "Create saved draft"}</Button>
    </form><p className="mt-3 text-xs text-muted-foreground">Create a draft, then write and explicitly save revisions. AI drafting is available inside each editor after you supply permitted reporting notes.</p></CardContent></Card>
    <div className="flex items-center justify-between"><h2 className="font-semibold">Manual stories {data ? `(${data.total})` : ""}</h2><Button variant="outline" onClick={refresh}>Refresh list</Button></div>
    {!data && !error && <p role="status">Loading saved stories…</p>}
    {data?.items.length === 0 && <p className="text-sm text-muted-foreground">No manual stories yet. Create your first draft above.</p>}
    {data?.items.map(story => <Card key={story.id}><CardContent className="flex flex-wrap items-center justify-between gap-4 p-5"><div><Link className="font-semibold underline" href={`/manual-writing/${story.id}`}>{story.title}</Link><p className="mt-2 text-xs text-muted-foreground">{story.language.toUpperCase()} · {story.status} · Revision {story.version} · {localDate(story.updated_at)}</p>{story.warnings.map(warning => <p key={warning} className="mt-1 text-xs text-amber-800">{warning}</p>)}</div><Button asChild variant="outline"><Link href={`/manual-writing/${story.id}`}>Open editor</Link></Button></CardContent></Card>)}
    <div className="flex gap-3">{cursor && <Button variant="outline" onClick={() => setCursor(null)}>First page</Button>}{data?.next_cursor && <Button variant="outline" onClick={() => setCursor(data.next_cursor)}>Next stories</Button>}</div>
  </div>;
}
