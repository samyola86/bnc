"use client";
import { useState } from "react";
import Link from "next/link";
import { Account, useSession } from "./session";
import { newsroom, localDate } from "../feeds/api";
import { useRemote } from "../feeds/use-remote";
import { Field, Feedback, fieldClass } from "../feeds/shared";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Task = { id: string; title: string; description: string; assignee_id: string; assignee_name: string; creator_id: string; story_id: string | null; story_origin_item_id: string | null; priority: string; status: string; due_at: string | null; completed_at: string | null; created_at: string; updated_at: string; feedback: string };
export function TasksWorkspace() {
  const { user } = useSession();
  const admin = user?.role === "SUPERADMIN";
  const [all, setAll] = useState(false);
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [history, setHistory] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const { data, error: loadError, refresh } = useRemote<{ items: Task[] }>(`tasks?all_tasks=${all}`, 15000);
  async function status(task: Task, status: string) {
    setError(null);
    try { await newsroom(`tasks/${task.id}/status`, { method: "POST", body: { status } }); refresh(); }
    catch (e) { setError((e as Error).message); }
  }
  return <><PageHeader title="My Tasks" description="Assignments, deadlines and feedback. Task completion does not imply publication." action={admin ? <Button onClick={() => setEditing("new")}>Assign task</Button> : undefined} />
    <Feedback error={error ?? loadError} />{admin && <label className="mb-5 flex gap-2 text-sm"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} />View all newsroom workloads</label>}
    {admin && editing && <TaskForm key={editing === "new" ? "new" : editing.id} task={editing === "new" ? undefined : editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
    {history !== null && <Card className="mb-5"><CardContent className="p-4"><Button variant="ghost" onClick={() => setHistory(null)}>Close history</Button><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(history, null, 2)}</pre></CardContent></Card>}
    <div className="space-y-4">{data?.items.map(task => <Card key={task.id}><CardContent className="space-y-3 p-5"><div className="flex justify-between gap-4"><h2 className="font-semibold">{task.title}</h2><span className="text-xs">{task.priority} · {task.status.replaceAll("_", " ")}</span></div><p className="whitespace-pre-wrap text-sm">{task.description}</p><p className="text-xs text-muted-foreground">Assigned to {task.assignee_name} · Due: {localDate(task.due_at)} · Created: {localDate(task.created_at)} · Updated: {localDate(task.updated_at)}{task.completed_at ? ` · Completed: ${localDate(task.completed_at)}` : ""}</p>{task.feedback && <p className="rounded bg-muted p-3 text-sm">Feedback: {task.feedback}</p>}<div className="flex flex-wrap items-center gap-2">{task.story_id && <Button asChild variant="outline"><Link href={task.story_origin_item_id ? `/news-feeds/drafts/${task.story_id}` : `/manual-writing/${task.story_id}`}>Open story</Link></Button>}<select aria-label={`Status for ${task.title}`} className={`${fieldClass} w-auto`} value={task.status} onChange={e => status(task, e.target.value)}>{["TO_DO", "IN_PROGRESS", "IN_REVIEW", "COMPLETED"].map(s => <option key={s}>{s}</option>)}</select>{admin && <Button variant="outline" onClick={() => setEditing(task)}>Edit / reassign</Button>}<Button variant="ghost" onClick={async () => { try { setHistory(await newsroom(`tasks/${task.id}/history`)); } catch (e) { setError((e as Error).message); } }}>History</Button></div></CardContent></Card>)}{data && !data.items.length && <p className="rounded border p-6 text-sm text-muted-foreground">No tasks assigned.</p>}</div>
  </>;
}

function TaskForm({ task, onCancel, onSaved }: { task?: Task; onCancel: () => void; onSaved: () => void }) {
  const { data } = useRemote<{ items: Account[] }>("admin/users?status=active");
  const [form, setForm] = useState({ title: task?.title ?? "", description: task?.description ?? "", assignee_id: task?.assignee_id ?? "", story_id: task?.story_id ?? "", priority: task?.priority ?? "MEDIUM", due: task?.due_at ? new Date(new Date(task.due_at).getTime() + 21600000).toISOString().slice(0, 16) : "", feedback: task?.feedback ?? "" });
  const [error, setError] = useState<string | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const { due, ...fields } = form;
      await newsroom(task ? `tasks/${task.id}` : "tasks", { method: task ? "PATCH" : "POST", body: { ...fields, story_id: fields.story_id || null, due_at: due ? new Date(`${due}:00+06:00`).toISOString() : null } }); onSaved();
    } catch (e) { setError((e as Error).message); }
  }
  return <Card className="mb-5"><CardContent className="p-5"><Feedback error={error} /><form onSubmit={save} className="grid gap-4 md:grid-cols-2">{(["title", "description", "story_id", "feedback"] as const).map(key => <Field key={key} label={key.replaceAll("_", " ")}><input className={fieldClass} required={key === "title"} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></Field>)}<Field label="Assigned user"><select required className={fieldClass} value={form.assignee_id} onChange={e => setForm({ ...form, assignee_id: e.target.value })}><option value="">Select user</option>{data?.items.filter(u => u.role !== "SUPERADMIN").map(u => <option key={u.id} value={u.id}>{u.name} · {u.role}</option>)}</select></Field><Field label="Priority"><select className={fieldClass} value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>{["LOW", "MEDIUM", "HIGH", "URGENT"].map(p => <option key={p}>{p}</option>)}</select></Field><Field label="Due · Dhaka time"><input type="datetime-local" className={fieldClass} value={form.due} onChange={e => setForm({ ...form, due: e.target.value })} /></Field><div className="flex items-end gap-2"><Button type="submit">Save assignment</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div></form></CardContent></Card>;
}
