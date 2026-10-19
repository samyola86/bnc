"use client";
import { useState } from "react";
import { Account, Role } from "./session";
import { newsroom, localDate } from "../feeds/api";
import { useRemote } from "../feeds/use-remote";
import { Field, Feedback, fieldClass } from "../feeds/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/layout/page-header";

const roles: Role[] = ["SUPERADMIN", "EDITOR", "CONTENT_WRITER"];
export function UsersWorkspace() {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("all");
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { data, error: loadError, refresh } = useRemote<{ items: Account[] }>(`admin/users?${new URLSearchParams({ query, status, ...(role ? { role } : {}) })}`);
  async function action(user: Account, action: string, value?: string) {
    if (!window.confirm(`${action === "reset-password" ? "Send a password reset email and revoke sessions for" : `Mark ${value}`} ${user.name}?`)) return;
    setError(null); setNotice(null);
    try { await newsroom(`admin/users/${user.id}/${action}`, { method: "POST", body: value ? { status: value } : {} }); refresh(); setNotice("Account updated."); }
    catch (e) { setError((e as Error).message); }
  }
  return <><PageHeader title="User Management" description="Manage individual newsroom accounts. Account deletion preserves editorial and audit history." action={<Button onClick={() => setEditing("new")}>Create user</Button>} />
    <Feedback error={error ?? loadError} message={notice} />
    {editing && <AccountForm key={editing === "new" ? "new" : editing.id} user={editing === "new" ? undefined : editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />}
    <div className="mb-5 grid gap-4 md:grid-cols-3"><Field label="Search name, username or email"><input className={fieldClass} value={query} onChange={e => setQuery(e.target.value)} /></Field><Field label="Role"><select className={fieldClass} value={role} onChange={e => setRole(e.target.value)}><option value="">All roles</option>{roles.map(r => <option key={r}>{r}</option>)}</select></Field><Field label="Account status"><select className={fieldClass} value={status} onChange={e => setStatus(e.target.value)}>{["all", "active", "suspended", "deleted"].map(s => <option key={s}>{s}</option>)}</select></Field></div>
    <Card><CardContent className="overflow-x-auto p-0"><table className="w-full min-w-[800px] text-left text-sm"><thead><tr>{["Account", "Role / status", "Dates", "Actions"].map(t => <th key={t} className="border-b p-4">{t}</th>)}</tr></thead><tbody>{data?.items.map(user => <tr key={user.id} className="border-b align-top"><td className="p-4 font-medium">{user.name}<p className="mt-1 text-xs text-muted-foreground">{user.username ?? "Legacy identity"}<br />{user.email}</p></td><td className="p-4">{user.role}<p className="mt-1 text-xs">{user.status} · MFA {user.mfa_enabled ? "enrolled" : "not enrolled"}</p></td><td className="p-4 text-xs">Created: {localDate(user.created_at)}<br />Last login: {localDate(user.last_login)}</td><td className="flex max-w-md flex-wrap gap-2 p-4">{!user.deleted_at && <><Button size="sm" variant="outline" onClick={() => setEditing(user)}>Edit / role</Button><Button size="sm" variant="outline" onClick={() => action(user, "status", user.active ? "suspended" : "active")}>{user.active ? "Suspend" : "Reactivate"}</Button><Button size="sm" variant="outline" onClick={() => action(user, "reset-password")}>Reset password</Button><Button size="sm" variant="ghost" onClick={() => action(user, "status", "deleted")}>Soft-delete</Button></>}<a className="p-2 text-xs underline" href={`/audit?user=${user.id}`}>Activity history</a></td></tr>)}</tbody></table></CardContent></Card>
  </>;
}

function AccountForm({ user, onCancel, onSaved }: { user?: Account; onCancel: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: user?.name ?? "", email: user?.email ?? "", username: user?.username ?? "", role: user?.role ?? "CONTENT_WRITER", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const { password, ...account } = form;
      await newsroom(user ? `admin/users/${user.id}` : "admin/users", { method: user ? "PATCH" : "POST", body: user ? account : { ...account, password } });
      setForm({ ...form, password: "" }); onSaved();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <Card className="mb-6"><CardContent className="p-5"><Feedback error={error} /><form onSubmit={save} className="grid gap-4 md:grid-cols-2">{(["name", "email", "username"] as const).map(key => <Field key={key} label={key}><input required type={key === "email" ? "email" : "text"} className={fieldClass} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></Field>)}<Field label="Role"><select className={fieldClass} value={form.role} onChange={e => setForm({ ...form, role: e.target.value as Role })}>{roles.map(role => <option key={role}>{role}</option>)}</select></Field>{!user && <Field label="Initial password (12+ characters)"><input type="password" required minLength={12} maxLength={256} autoComplete="new-password" className={fieldClass} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></Field>}<div className="flex items-end gap-2"><Button type="submit" disabled={busy}>Save account</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div></form></CardContent></Card>;
}

export function AuditWorkspace({ initialUser = "" }: { initialUser?: string }) {
  const [filter, setFilter] = useState(initialUser);
  const { data, error } = useRemote<{ items: { id: string; actor_id: string | null; action: string; resource_id: string; created_at: string; details: unknown }[] }>(`admin/audit${filter ? `?user_id=${encodeURIComponent(filter)}` : ""}`);
  return <><PageHeader title="Audit History" description="Administrative, authentication and editorial activity. Latest 200 events." /><Field label="Filter by user ID (optional)"><input className={fieldClass} value={filter} onChange={e => setFilter(e.target.value)} /></Field><Feedback error={error} /><div className="mt-5 space-y-3">{data?.items.map(event => <Card key={event.id}><CardContent className="p-4 text-sm"><p className="font-semibold">{event.action} · {localDate(event.created_at)}</p><p className="mt-1 break-all text-xs text-muted-foreground">Actor: {event.actor_id ?? "Unauthenticated"} · Resource: {event.resource_id}</p><pre className="mt-3 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(event.details, null, 2)}</pre></CardContent></Card>)}</div></>;
}
