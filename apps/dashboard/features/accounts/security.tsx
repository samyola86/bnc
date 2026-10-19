"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "./session";
import { newsroom } from "../feeds/api";
import { Feedback, Field, fieldClass } from "../feeds/shared";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";

export function AccountSecurity() {
  const { user, reload } = useSession();
  const router = useRouter();
  const [uri, setUri] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  async function perform(action: string) {
    setError(null);
    try {
      if (action === "setup") setUri((await newsroom<{ uri: string }>("auth/mfa/setup", { method: "POST" })).uri);
      if (action === "verify") { await newsroom("auth/mfa/verify", { method: "POST", body: { code } }); setUri(""); setCode(""); reload(); setNotice("MFA enabled. Other sessions were revoked."); }
      if (action === "renew") { await newsroom("auth/renew", { method: "POST" }); setNotice("Session renewed."); }
      if (action === "logout-all" && window.confirm("Sign out of all devices, including this one?")) { await newsroom("auth/logout-all", { method: "POST" }); router.replace("/login"); }
    } catch (e) { setError((e as Error).message); }
  }
  return <><PageHeader title="My Account & Security" description="Individual sessions and authenticator verification." /><Feedback error={error} message={notice} /><div className="max-w-xl space-y-5 rounded border bg-card p-6"><p>{user?.name} · {user?.role}</p><p className="text-sm">MFA: {user?.mfa_enabled ? "Enrolled" : "Not enrolled"}</p>{!user?.mfa_enabled && <Button onClick={() => perform("setup")}>Enroll authenticator</Button>}{uri && <><a className="block break-all text-sm text-primary underline" href={uri}>{uri}</a><Field label="Authenticator code"><input inputMode="numeric" className={fieldClass} value={code} onChange={e => setCode(e.target.value)} /></Field><Button onClick={() => perform("verify")}>Verify and enable MFA</Button></>}<div className="flex flex-wrap gap-3"><Button variant="outline" onClick={() => perform("renew")}>Renew session</Button><Button variant="outline" onClick={() => perform("logout-all")}>Sign out all devices</Button></div></div></>;
}
