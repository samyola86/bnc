import type { NextRequest } from "next/server";
import { validWriteOrigin } from "@/lib/auth-origins";

const uuid = "[0-9a-fA-F-]{36}";
const routes: Record<string, RegExp[]> = {
  GET: [/^feeds\/summary$/, /^stories$/, new RegExp(`^stories/${uuid}/(versions|ai-jobs)$`), new RegExp(`^ai/jobs/${uuid}$`), /^sources$/, /^feeds\/items$/, /^ingestion\/settings$/, new RegExp(`^ingestion/jobs/${uuid}$`), new RegExp(`^stories/${uuid}$`)],
  POST: [/^stories$/, new RegExp(`^stories/${uuid}/ai-draft$`), /^sources$/, /^sources\/test$/, new RegExp(`^sources/${uuid}/(test|collect|archive|restore)$`), new RegExp(`^feeds/items/${uuid}/draft$`)],
  PATCH: [/^ingestion\/settings$/, new RegExp(`^sources/${uuid}$`), new RegExp(`^feeds/items/${uuid}$`), new RegExp(`^stories/${uuid}$`)],
};

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  const extra = request.method === "GET" ? /^(publishing\/queue|media\/[0-9a-fA-F-]{36})$/ : request.method === "POST" ? /^(media|stories\/[0-9a-fA-F-]{36}\/queue|publishing\/queue\/[0-9a-fA-F-]{36}\/cancel)$/ : null;
  const accounts = /^(auth\/(login|logout|logout-all|me|renew|forgot-password|reset-password|mfa\/setup|mfa\/verify)|admin\/(users|audit|system-status|users\/[0-9a-fA-F-]{36}(\/(status|reset-password))?)|tasks(\/[0-9a-fA-F-]{36}(\/(status|history))?)?|publishing\/requests\/[0-9a-fA-F-]{36}|stories\/[0-9a-fA-F-]{36}\/(readiness|submit-review|approve|request-changes|reject|ready))$/;
  const newsBite = request.method === "GET" ? /^news-bite\/templates$/.test(path) : request.method === "POST" && new RegExp(`^stories/${uuid}/news-bite/preview$`).test(path);
  if (!newsBite && !accounts.test(path) && !extra?.test(path) && !routes[request.method]?.some(pattern => pattern.test(path))) {
    return Response.json({ error: { message: "Route not found" } }, { status: 404 });
  }
  if (request.method !== "GET") {
    if (!validWriteOrigin(request.headers)) {
      return Response.json({ error: { message: "A same-origin editor request is required" } }, { status: 403 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return Response.json({ error: { message: "Use application/json" } }, { status: 415 });
    }
  }
  let body: string | undefined;
  if (request.method !== "GET" && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      length += chunk.value.length;
      if (length > (path === "media" ? 4 * 1024 * 1024 + 1024 : 512 * 1024)) {
        await reader.cancel();
        return Response.json({ error: { message: "The editor request is too large" } }, { status: 413 });
      }
      chunks.push(chunk.value);
    }
    body = Buffer.concat(chunks).toString("utf8") || "{}";
  }
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/api/v1/${path}${request.nextUrl.search}`, {
      method: request.method, body, cache: "no-store", signal: AbortSignal.timeout(60000),
      headers: { Cookie: request.headers.get("cookie") ?? "", Origin: request.headers.get("origin") ?? "", "Sec-Fetch-Site": request.headers.get("sec-fetch-site") ?? "", "Content-Type": "application/json" },
    });
    const headers = new Headers({ "Content-Type": response.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
    for (const cookie of response.headers.getSetCookie()) headers.append("Set-Cookie", cookie);
    return new Response(await response.arrayBuffer(), { status: response.status, headers });
  } catch {
    return Response.json({ error: { message: "The editorial API did not respond. Check the API and worker services" } }, { status: 503 });
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH };
