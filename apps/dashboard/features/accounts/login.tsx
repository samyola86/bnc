"use client";
import Link from "next/link";
import { ArrowRight, Eye, EyeOff, LockKeyhole, UserRound } from "lucide-react";
import { useState } from "react";
import { AuthenticatorSetup } from "./authenticator-setup";
import { useRouter } from "next/navigation";
import { newsroom } from "../feeds/api";
import { Button } from "@/components/ui/button";
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
  const [showPassword, setShowPassword] = useState(false);
  const [logoMissing, setLogoMissing] = useState(false);
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
  return <main className="bnc-login">
    <div className="bnc-login-layout">
      <section className="bnc-login-brand" aria-label="Bangladesh News Corporation">
        {logoMissing ? <div className="bnc-login-logo-fallback"><strong>BNC</strong><span>Bangladesh News Corporation</span></div> :
          /* eslint-disable-next-line @next/next/no-img-element -- local brand artwork at its original aspect ratio */
          <img className="bnc-login-logo" src="/images/bnc-logo.png" alt="BNC — Bangladesh News Corporation" width={250} height={250} onError={() => setLogoMissing(true)} />}
        <p>Trusted News.<br />A Stronger Bangladesh.</p>
        <div className="bnc-login-accent" />
      </section>
      <section className="bnc-login-panel" aria-labelledby="login-heading">
        <header><p className="bnc-login-welcome">Welcome to</p><h1 id="login-heading">BNC</h1><p className="bnc-login-company">Bangladesh News Corporation</p></header>
        <p className="bnc-login-intro">{mfa ? "Secure your newsroom access." : "Sign in to access the newsroom."}</p>
        <Feedback error={error} message={notice} />
        <form onSubmit={login} className="bnc-login-form">
          {mfa ? <>
            {uri ? <AuthenticatorSetup uri={uri} /> : <p className="text-sm leading-6">Enter the current six-digit code from your authenticator.</p>}
            <label htmlFor="login-code">Authenticator code</label>
            <input id="login-code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" required className="bnc-login-input" value={code} onChange={e => setCode(e.target.value)} />
          </> : <>
            <div className="bnc-login-field"><label htmlFor="login-identity">Account Name</label><div className="bnc-login-input-wrap"><UserRound aria-hidden="true" size={20} /><input id="login-identity" aria-label="Email or username" autoComplete="username" placeholder="Enter your account name" required className="bnc-login-input" value={identity} onChange={e => setIdentity(e.target.value)} /></div></div>
            <div className="bnc-login-field"><label htmlFor="login-password">Password</label><div className="bnc-login-input-wrap"><LockKeyhole aria-hidden="true" size={20} /><input id="login-password" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="Enter your password" required className="bnc-login-input" value={password} onChange={e => setPassword(e.target.value)} /><button type="button" className="bnc-login-reveal" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <Eye size={20} /> : <EyeOff size={20} />}</button></div></div>
          </>}
          <button disabled={busy} type="submit" className="bnc-login-submit">{busy ? "Checking…" : mfa ? "Verify authenticator" : "Sign in"}<ArrowRight aria-hidden="true" size={21} /></button>
          {!mfa && <button type="button" className="bnc-login-forgot" disabled={busy || !identity.trim()} onClick={forgot}>Forgot password?</button>}
        </form>
        <footer className="bnc-login-footer"><span />BNC Internal Use Only<span /></footer>
      </section>
    </div>
  </main>;
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
