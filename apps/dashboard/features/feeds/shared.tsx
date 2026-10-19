import type { ReactNode } from "react";

export const fieldClass = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm disabled:bg-muted";
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-sm font-medium"><span>{label}</span>{children}</label>;
}
export function Feedback({ error, message }: { error?: string | null; message?: string | null }) {
  return <>{error && <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p>}{message && <p role="status" className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{message}</p>}</>;
}
export function Status({ children }: { children: ReactNode }) {
  return <span className="inline-flex rounded-full bg-muted px-2 py-1 text-[11px] font-medium tracking-wide">{children}</span>;
}
