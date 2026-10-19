"use client";
import { cloneElement, isValidElement, useContext, useId, type ReactElement, type ReactNode } from "react";
import { ValidationContext } from "../stories/readiness";

export const fieldClass = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm disabled:bg-muted";
export function Field({ label, children, validationKey, group = false }: { label: string; children: ReactNode; validationKey?: string; group?: boolean }) {
  const { errors, attempted } = useContext(ValidationContext);
  const hintId = useId();
  const message = validationKey ? errors[validationKey] : undefined;
  const control = isValidElement(children) && typeof children.type === "string" && ["input", "textarea", "select"].includes(children.type)
    ? cloneElement(children as ReactElement<{ "aria-label"?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>, { "aria-label": label, "aria-invalid": !!message, "aria-describedby": message ? hintId : undefined }) : children;
  const Tag = group ? "div" : "label";
  return <Tag data-field={validationKey} data-invalid={!!message} className={`block text-sm font-medium ${message ? attempted ? "rounded-md border border-red-400 bg-red-50 p-2 [&_input]:border-red-400 [&_textarea]:border-red-400" : "rounded-md border border-amber-200 bg-amber-50/40 p-2 [&_input]:border-amber-300 [&_textarea]:border-amber-300" : ""}`}><span>{label}{message && <span aria-hidden="true" className="ml-2">⚠</span>}</span>{control}{message && <small id={hintId} role={attempted ? "alert" : undefined} className={`mt-1 block font-normal ${attempted ? "text-red-800" : "text-amber-900"}`}>{message}</small>}</Tag>;
}
export function Feedback({ error, message }: { error?: string | null; message?: string | null }) {
  return <>{error && <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p>}{message && <p role="status" className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{message}</p>}</>;
}
export function Status({ children }: { children: ReactNode }) {
  return <span className="inline-flex rounded-full bg-muted px-2 py-1 text-[11px] font-medium tracking-wide">{children}</span>;
}
