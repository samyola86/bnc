import type { NextRequest } from "next/server";

const uuid = "[0-9a-fA-F-]{36}";
const routes: Record<string, RegExp[]> = {
  GET: [/^sources$/, /^feeds\/items$/, /^ingestion\/settings$/, new RegExp(`^ingestion/jobs/${uuid}$`), new RegExp(`^stories/${uuid}$`)],
  POST: [/^sources$/, /^sources\/test$/, new RegExp(`^sources/${uuid}/(test|collect)$`), new RegExp(`^feeds/items/${uuid}/draft$`)],
  PATCH: [/^ingestion\/settings$/, new RegExp(`^sources/${uuid}$`), new RegExp(`^feeds/items/${uuid}$`), new RegExp(`^stories/${uuid}$`)],
};

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!routes[request.method]?.some(pattern => pattern.test(path))) {
    return Response.json({ error: { message: "Route not found" } }, { status: 404 });
  }
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    if (!origin || new URL(origin).host !== request.headers.get("host") || request.headers.get("sec-fetch-site") === "cross-site") {
      return Response.json({ error: { message: "A same-origin editor request is required" } }, { status: 403 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return Response.json({ error: { message: "Use application/json" } }, { status: 415 });
    }
  }
  const token = process.env.INGESTION_API_TOKEN;
  if (!token) return Response.json({ error: { message: "The editor service credential is not configured" } }, { status: 503 });
  let body: string | undefined;
  if (request.method !== "GET" && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      length += chunk.value.length;
      if (length > 512 * 1024) {
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
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: { message: "The editorial API did not respond. Check the API and worker services" } }, { status: 503 });
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH };
