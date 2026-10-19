"use client";
import { createContext } from "react";
import type { Credit } from "../feeds/api";
import type { StoryDetails } from "./story-details";

export const ValidationContext = createContext<{ errors: Record<string, string>; attempted: boolean }>({ errors: {}, attempted: false });
export function readinessFor(title: string, body: string, category: string, tags: string, language: string, details: StoryDetails, credits: Credit[]) {
  const checks: Record<string, [boolean, string]> = {
    title: [!!title.trim(), "Add a headline"], body: [!!body.trim(), "Add article content"],
    category: [!!category.trim(), "Add a category"], tags: [tags.split(",").some(t => t.trim()), "Add at least one tag"],
    contributors: [details.contributors.split(",").some(c => c.trim()), "Add a contributor"],
    destinations: [details.destinations.length > 0, "Select a publishing destination"],
    format: [["article", "news_bite"].includes(details.format), "Select a valid format"],
    language: [["bn", "en"].includes(language), "Select a valid language"],
  };
  if (details.destinations.includes("instagram")) checks.cover_image_id = [!!details.cover_image_id, "Add an Instagram cover image"];
  if (details.schedule) checks.scheduled_at = [new Date(`${details.schedule}:00+06:00`).getTime() > Date.now(), "Choose a future publication time in Dhaka"];
  if (credits.some(c => c.rights_status === "prohibited")) checks.credits_rights = [false, "Resolve prohibited source usage rights"];
  const errors = Object.fromEntries(Object.entries(checks).filter(([, [valid]]) => !valid).map(([key, [, message]]) => [key, message]));
  return { errors, complete: Object.keys(checks).length - Object.keys(errors).length, total: Object.keys(checks).length };
}
export function focusField(key: string) {
  const element = document.querySelector<HTMLElement>(`[data-field="${key}"]`);
  element?.scrollIntoView({ behavior: "smooth", block: "center" });
  element?.querySelector<HTMLElement>("input, textarea, select, button")?.focus({ preventScroll: true });
}
export function ReadinessPanel({ result }: { result: ReturnType<typeof readinessFor> }) {
  return <section aria-label="Publishing Readiness" className="mb-5 rounded-lg border bg-card p-4"><p role="status" className="font-semibold">Publishing Readiness: {result.complete} of {result.total} complete</p>{Object.keys(result.errors).length ? <ul className="mt-3 space-y-1 text-sm text-amber-900">{Object.entries(result.errors).map(([key, text]) => <li key={key}><button type="button" className="underline underline-offset-2" onClick={() => focusField(key)}>⚠ {text}</button></li>)}</ul> : <p className="mt-2 text-sm text-emerald-800">Ready to submit for editorial review.</p>}</section>;
}
