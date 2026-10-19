/** Server-side transport boundary. Python remains the authorization authority. */
import { API_UNAVAILABLE_MESSAGE } from "./service-errors";

const requestHeaders = [
  "accept",
  "authorization",
  "content-type",
  "idempotency-key",
  "range",
  "if-range",
];
const responseHeaders = [
  "content-type",
  "content-disposition",
  "content-range",
  "accept-ranges",
  "www-authenticate",
  "retry-after",
];

type Options = {
  origin?: string;
  fetcher?: typeof fetch;
  timeoutMs?: number;
};

export async function proxyApiRequest(
  request: Request,
  area: string,
  path: string[],
  options: Options = {},
): Promise<Response> {
  const privacyHeaders = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  };
  if (
    !["candidate", "hr"].includes(area) ||
    !path.length ||
    path.some(
      (segment) =>
        !segment || /[/\\\0]/.test(segment) || [".", ".."].includes(segment),
    )
  ) {
    return Response.json(
      { detail: "API route not found" },
      { status: 404, headers: privacyHeaders },
    );
  }
  try {
    const origin =
      options.origin ?? process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
    const target = new URL(origin);
    if (
      !["http:", "https:"].includes(target.protocol) ||
      target.username ||
      target.password
    ) {
      throw new Error("Invalid API origin");
    }
    target.pathname = `/${area}/${path.map(encodeURIComponent).join("/")}`;
    target.search = new URL(request.url).search;
    target.hash = "";
    const headers = new Headers();
    for (const name of requestHeaders) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    // Stream multipart uploads unchanged, preserving their boundary and size limits.
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      cache: "no-store",
      // Avoid ambient cookies and HTTP-auth challenge replay of streamed bodies.
      credentials: "omit",
      redirect: "manual",
      signal: AbortSignal.any([
        request.signal,
        AbortSignal.timeout(options.timeoutMs ?? 25000),
      ]),
      duplex: "half",
    };
    const fetcher = options.fetcher ?? fetch;
    const upstream = await fetcher(target, init);
    const outputHeaders = new Headers(privacyHeaders);
    for (const name of responseHeaders) {
      const value = upstream.headers.get(name);
      if (value !== null) outputHeaders.set(name, value);
    }
    // HTTP status and body (including validation/auth failures) belong to FastAPI.
    return new Response(upstream.body, {
      status: upstream.status,
      headers: outputHeaders,
    });
  } catch {
    // Do not echo connection details, submitted credentials or private server paths.
    return Response.json(
      { detail: API_UNAVAILABLE_MESSAGE, code: "api_unavailable" },
      { status: 503, headers: { ...privacyHeaders, "Retry-After": "3" } },
    );
  }
}
