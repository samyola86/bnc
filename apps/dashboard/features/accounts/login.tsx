"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { newsroom } from "../feeds/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Feedback, fieldClass } from "../feeds/shared";
import { Account, useSession } from "./session";

export function LoginForm() {
  const router = useRouter();
  const { reload } = useSession();
  const [identity, setIdentity] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfa, setMfa] = useState(false);
  const [uri, setUri] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      if (mfa) { await newsroom("auth/mfa/verify", { method: "POST", body: { code } }); }
      else {
        const result = await newsroom<{ user: Account; mfa_required: boolean }>("auth/login", { method: "POST", body: { identity, password } });
        setPassword("");
        if (result.mfa_required) {
          setMfa(true);
          if (!result.user.mfa_enabled) setUri((await newsroom<{ uri: string }>("auth/mfa/setup", { method: "POST" })).uri);
          return;
        }
      }
      reload(); router.replace("/");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function forgot() {
    setBusy(true); setError(null);
    try { const result = await newsroom<{ message: string }>("auth/forgot-password", { method: "POST", body: { identity } }); setNotice(result.message); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-lg px-6 py-16"><Card><CardHeader><CardTitle>BNC newsroom sign in</CardTitle></CardHeader><CardContent>
    <Feedback error={error} message={notice} /><form onSubmit={login} className="space-y-5">
      {mfa ? <><p className="text-sm">Enter the current six-digit code from your authenticator.</p>{uri && <div className="space-y-3 rounded border bg-muted p-3 text-sm"><p>Add this account to an authenticator using its setup link, or enter the secret shown in the link manually.</p><a className="break-all text-primary underline" href={uri}>{uri}</a></div>}<Field label="Authenticator code"><input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" required className={fieldClass} value={code} onChange={e => setCode(e.target.value)} /></Field></> : <>
      <Field label="Email or username"><input autoComplete="username" required className={fieldClass} value={identity} onChange={e => setIdentity(e.target.value)} /></Field>
      <Field label="Password"><input type="password" autoComplete="current-password" required className={fieldClass} value={password} onChange={e => setPassword(e.target.value)} /></Field></>}
      <Button disabled={busy} type="submit">{busy ? "Checking…" : mfa ? "Verify authenticator" : "Sign in"}</Button>
      {!mfa && <Button type="button" variant="ghost" disabled={busy || !identity.trim()} onClick={forgot}>Reset password</Button>}
    </form><p className="mt-6 text-xs leading-5 text-muted-foreground">The first Superadmin must be initialized on the trusted API host. No default administrator password exists.</p>
  </CardContent></Card></div>;
}

export function ResetPasswordForm() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function reset(event: React.FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
      await newsroom("auth/reset-password", { method: "POST", body: { token, password } });
      window.history.replaceState(null, "", "/reset-password"); setPassword(""); setNotice("Password updated. Sign in with your new password.");
    } catch (e) { setError((e as Error).message); }
  }
  return <div className="mx-auto max-w-lg p-10"><h1 className="mb-6 text-2xl font-bold">Reset BNC password</h1><Feedback error={error} message={notice} /><form onSubmit={reset} className="space-y-4"><Field label="New password (12+ characters)"><input type="password" autoComplete="new-password" required minLength={12} maxLength={256} className={fieldClass} value={password} onChange={e => setPassword(e.target.value)} /></Field><Button type="submit">Set password</Button><Link className="ml-4 text-sm underline" href="/login">Sign in</Link></form></div>;
}
