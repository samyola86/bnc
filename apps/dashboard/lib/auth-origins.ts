// Server-side only. Never infer trusted origins from forwarding headers.
export function trustedAuthOrigins(env: Record<string, string | undefined> = process.env): string[] {
  const extra: unknown = JSON.parse(env.AUTH_ADDITIONAL_ORIGINS || "[]");
  if (!Array.isArray(extra)) throw new Error("AUTH_ADDITIONAL_ORIGINS must be a JSON array");
  const origins: unknown[] = [env.AUTH_ORIGIN || "http://localhost:3000", ...extra];
  return [...new Set(origins.map(value => {
    if (typeof value !== "string" || !/^https?:\/\/[a-z0-9.-]+(?::[0-9]+)?$/.test(value)) {
      throw new Error("Use exact trusted origins without paths or wildcards");
    }
    const url = new URL(value);
    if (url.port === "0" || (url.protocol === "http:" && !["localhost", "127.0.0.1"].includes(url.hostname))) {
      throw new Error("Public trusted origins must use HTTPS");
    }
    return value;
  }))];
}

export function validWriteOrigin(headers: Headers): boolean {
  const origin = headers.get("origin");
  return !!origin && trustedAuthOrigins().includes(origin)
    && new URL(origin).host === headers.get("host")
    && headers.get("sec-fetch-site") !== "cross-site";
}
