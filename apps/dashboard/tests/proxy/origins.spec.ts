import { test, expect } from "@playwright/test";
import type { NextRequest } from "next/server";
import { POST } from "../../app/api/newsroom/[...path]/route";
import { trustedAuthOrigins } from "../../lib/auth-origins";

const local = "http://localhost:3000";
const publicOrigin = "https://trustable-detail-drift.ngrok-free.dev";
test.describe.configure({ mode: "serial" });

for (const origin of [local, publicOrigin]) {
  test(`proxy forwards session and origin for ${origin}`, async () => {
    const previous = process.env.AUTH_ADDITIONAL_ORIGINS;
    process.env.AUTH_ADDITIONAL_ORIGINS = JSON.stringify([publicOrigin]);
    const originalFetch = global.fetch;
    let captured: RequestInit | undefined;
    global.fetch = async (_url, init) => {
      captured = init;
      return new Response('{"ok":true}', { headers: {
        "Set-Cookie": `bnc_session=rotated; Path=/; HttpOnly; SameSite=Strict${origin.startsWith("https:") ? "; Secure" : ""}`,
      } });
    };
    try {
      const request = new Request(`${origin}/api/newsroom/auth/renew`, { method: "POST", headers: {
        Host: new URL(origin).host, Origin: origin, Cookie: "bnc_session=test-session",
        "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin",
        "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "http",
      }, body: "{}" }) as NextRequest;
      Object.defineProperty(request, "nextUrl", { value: new URL(request.url) });
      const response = await POST(request, { params: Promise.resolve({ path: ["auth", "renew"] }) });
      expect(response.status).toBe(200);
      const headers = new Headers(captured?.headers);
      expect(headers.get("cookie")).toBe("bnc_session=test-session");
      expect(headers.get("origin")).toBe(origin);
      expect(headers.get("x-forwarded-host")).toBeNull();
      expect(response.headers.get("set-cookie")).toContain("HttpOnly");
      expect(response.headers.get("set-cookie")).not.toContain("Domain=");
    } finally {
      global.fetch = originalFetch;
      if (previous === undefined) delete process.env.AUTH_ADDITIONAL_ORIGINS;
      else process.env.AUTH_ADDITIONAL_ORIGINS = previous;
    }
  });
}

for (const [origin, host, site] of [
  ["https://evil.example", "evil.example", "same-origin"],
  [publicOrigin, "localhost:3000", "same-origin"],
  [local, "localhost:3000", "cross-site"],
  ["not an origin", "localhost:3000", "same-origin"],
  ["", "localhost:3000", "same-origin"],
  ["http://trustable-detail-drift.ngrok-free.dev", new URL(publicOrigin).host, "same-origin"],
]) {
  test(`proxy blocks ${origin || "missing Origin"} / ${host} / ${site}`, async () => {
    const request = new Request(`${local}/api/newsroom/auth/login`, { method: "POST", headers: {
      Origin: origin, Host: host, "Sec-Fetch-Site": site, "Content-Type": "application/json",
      "X-Forwarded-Host": new URL(publicOrigin).host, "X-Forwarded-Proto": "https",
    }, body: "{}" }) as NextRequest;
    const response = await POST(request, { params: Promise.resolve({ path: ["auth", "login"] }) });
    expect(response.status).toBe(403);
  });
}

test("invalid origin configuration fails closed", () => {
  for (const value of ["*", "https://*.example.com", "https://example.com/path", "http://example.com"]) {
    expect(() => trustedAuthOrigins({ AUTH_ADDITIONAL_ORIGINS: JSON.stringify([value]) })).toThrow();
  }
});
