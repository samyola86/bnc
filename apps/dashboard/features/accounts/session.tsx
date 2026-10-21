"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { newsroom } from "../feeds/api";

export type Role = "SUPERADMIN" | "EDITOR" | "CONTENT_WRITER";
export type Account = { id: string; name: string; username: string; email: string; role: Role; active: boolean; status: string; mfa_enabled: boolean; last_login: string | null; created_at: string; deleted_at: string | null };
type Session = { user: Account; mfa_required: boolean };
const Context = createContext<{ user: Account | null; reload: () => void }>({ user: null, reload: () => {} });
export const useSession = () => useContext(Context);

export function SessionBoundary({ children, publicChildren }: { children: React.ReactNode; publicChildren: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [generation, setGeneration] = useState(0);
  const isPublic = ["/login", "/reset-password"].includes(path);
  const reload = () => setGeneration(v => v + 1);
  useEffect(() => {
    let active = true;
    const load = () => newsroom<Session>("auth/me").then(value => {
      if (active) { setSession(value); setLoading(false); }
      if (!isPublic && value.mfa_required) router.replace("/login");
    }).catch(() => {
      if (active) { setSession(null); setLoading(false); }
      if (!isPublic) router.replace("/login");
    });
    void load();
    const timer = setInterval(load, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [path, generation, isPublic, router]);
  const adminPath = ["/users", "/sources", "/settings", "/audit", "/intelligence-settings"].some(p => path === p);
  useEffect(() => {
    if (!isPublic && adminPath && session && session.user.role !== "SUPERADMIN") router.replace("/");
  }, [isPublic, adminPath, session, router]);
  return <Context.Provider value={{ user: session?.user ?? null, reload }}>
    {isPublic ? publicChildren : loading || !session || session.mfa_required ? <p className="p-10">Checking your session…</p> : adminPath && session.user.role !== "SUPERADMIN" ? <p className="p-10">Access restricted.</p> : children}
  </Context.Provider>;
}
