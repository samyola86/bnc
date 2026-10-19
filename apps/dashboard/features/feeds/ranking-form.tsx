import { Candidate } from "./api";
import { Field, fieldClass } from "./shared";
import { Button } from "@/components/ui/button";

export function RankingForm({ item, disabled, onSave }: { item: Candidate; disabled: boolean; onSave: (body: unknown) => void }) {
  return <form className="grid items-end gap-3 sm:grid-cols-2 xl:grid-cols-5" onSubmit={event => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const body: Record<string, number | null> = {};
    for (const key of ["bangladesh_relevance", "public_impact", "corroboration", "uniqueness", "rank_override"] as const) body[key] = data.get(key) === "" ? null : Number(data.get(key));
    onSave(body);
  }}>{([["bangladesh_relevance", "Bangladesh relevance"], ["public_impact", "Public impact"], ["corroboration", "Verified corroboration"], ["uniqueness", "Uniqueness"], ["rank_override", "Score override (optional)"]] as const).map(([key, label]) => <Field key={key} label={label}><input type="number" name={key} min={0} max={100} required={key !== "rank_override"} className={fieldClass} defaultValue={item[key] ?? ""} /></Field>)}<Button type="submit" variant="outline" size="sm" disabled={disabled}>Save ranking</Button></form>;
}
