export type Overview = { stories: number; in_review: number; approved: number; publications_pending: number };
export async function getOverview(): Promise<Overview | null> {
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/dashboard/overview`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    if (!response.ok) return null;
    return await response.json() as Overview;
  } catch { return null; }
}
