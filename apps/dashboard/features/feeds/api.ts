export async function newsroom<T>(path: string, options?: { method: string; body?: unknown }): Promise<T> {
  const response = await fetch(`/api/newsroom/${path}`, {
    method: options?.method ?? "GET", cache: "no-store", headers: { "Content-Type": "application/json" },
    body: options ? JSON.stringify(options.body ?? {}) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message ?? "The newsroom request failed");
  return data as T;
}

export function localDate(value: string | null) {
  return value ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", dateStyle: "medium", timeStyle: "short" }).format(new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)) : "Not supplied";
}

export type CollectionRun = { id: string; source_id: string; status: string; message: string; inserted: number; duplicates: number; skipped: number };
export type Credit = { source_id: string | null; publisher_name: string; original_url: string | null; attribution_text: string; is_original_reporting: boolean; rights_status: string; entry_method?: string };
export type Provenance = { source_id: string; publisher_name: string; original_url: string; rights_status: string; source_type: string; retrieved_at: string; published_at: string | null };
export type Source = {
  id: string; publisher: string; url: string; feed_url: string | null; source_type: string;
  language: string; category: string; rights: string; extraction_mode: string; polling_interval: number;
  active: boolean; notes: string; health: string; last_success: string | null; last_error: string | null;
  next_collection_at: string | null; can_collect: boolean; latest_run: CollectionRun | null;
};
export type SourcePage = { items: Source[]; total: number; next_cursor: string | null };
export type SourceTest = { supported: boolean; health: string; message: string; feeds: { url: string; title: string }[]; sample?: { title: string; url: string }[] };
export type Candidate = {
  id: string; title: string; excerpt: string; publisher: string; category: string; author: string;
  published_at: string | null; original_url: string; editorial_status: string; pinned: boolean;
  attributions: Provenance[]; score: number; rank_override: number | null; story_id: string | null;
  bangladesh_relevance: number; public_impact: number; corroboration: number; uniqueness: number;
};
export type CandidatePage = { items: Candidate[]; total: number; candidate_limit: number; next_cursor: string | null };
export type Draft = {
  id: string; origin_item_id: string; title: string; summary: string; body: string; category: string;
  version: number; status: string; credits: Credit[]; warnings: string[]; provenance: Provenance[];
};
