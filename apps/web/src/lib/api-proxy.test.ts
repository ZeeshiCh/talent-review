import test from "node:test";
import assert from "node:assert/strict";
import { proxyApiRequest } from "./api-proxy";
import { API_UNAVAILABLE_MESSAGE } from "./service-errors";

const origin = "http://127.0.0.1:8000";
const url = "http://localhost:3002/api/hr/session";

test("connection refusal returns private, readable 503 JSON", async () => {
  const request = new Request(url, {
    method: "POST",
    body: JSON.stringify({ password: "private-credential" }),
  });
  const response = await proxyApiRequest(request, "hr", ["session"], {
    origin,
    fetcher: async () => {
      throw new Error("ECONNREFUSED private-host");
    },
  });
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    detail: API_UNAVAILABLE_MESSAGE,
    code: "api_unavailable",
  });
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("retry-after"), "3");
});

test("timeout returns 503 without retrying a write", async () => {
  let calls = 0;
  const response = await proxyApiRequest(
    new Request(url, { method: "POST", body: "{}" }),
    "hr",
    ["session"],
    {
      origin,
      timeoutMs: 5,
      fetcher: async (_, init) => {
        calls++;
        await new Promise((_, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new Error("timed out")),
            { once: true },
          );
          setTimeout(() => reject(new Error("test deadline")), 100);
        });
        throw new Error("unreachable");
      },
    },
  );
  assert.equal(response.status, 503);
  assert.equal(calls, 1);
});

test("proxy forwards JSON, auth and query parameters but strips browser cookies", async () => {
  const response = await proxyApiRequest(
    new Request(url + "?offset=50", {
      method: "POST",
      headers: {
        Authorization: "Bearer local-token",
        "Content-Type": "application/json",
        Cookie: "private=cookie",
        Origin: "http://localhost:3002",
      },
      body: '{"email":"hr@example.test"}',
    }),
    "hr",
    ["session"],
    {
      origin,
      fetcher: async (input, init) => {
        assert.equal(String(input), origin + "/hr/session?offset=50");
        const headers = new Headers(init?.headers);
        assert.equal(headers.get("authorization"), "Bearer local-token");
        assert.equal(headers.get("cookie"), null);
        assert.equal(headers.get("origin"), null);
        assert.equal(
          await new Response(init?.body).text(),
          '{"email":"hr@example.test"}',
        );
        assert.equal(init?.redirect, "manual");
        assert.equal(init?.cache, "no-store");
        assert.equal(init?.credentials, "omit");
        return Response.json(
          { detail: "Invalid demo credentials" },
          {
            status: 401,
            headers: {
              "WWW-Authenticate": "Bearer",
              "Set-Cookie": "must-not-forward=secret",
            },
          },
        );
      },
    },
  );
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("www-authenticate"), "Bearer");
  assert.equal(response.headers.get("set-cookie"), null);
  assert.deepEqual(await response.json(), {
    detail: "Invalid demo credentials",
  });
});

test("multipart boundary, upload bytes and idempotency key survive the proxy", async () => {
  const form = new FormData();
  form.set(
    "file",
    new File([new Uint8Array([1, 2, 3])], "demo.wav", { type: "audio/wav" }),
  );
  const request = new Request(
    "http://localhost:3002/api/candidate/questions/id/audio",
    {
      method: "POST",
      headers: { "Idempotency-Key": "same-request" },
      body: form,
    },
  );
  const response = await proxyApiRequest(
    request,
    "candidate",
    ["questions", "id", "audio"],
    {
      origin,
      fetcher: async (input, init) => {
        const headers = new Headers(init?.headers);
        assert.match(
          headers.get("content-type") || "",
          /^multipart\/form-data; boundary=/,
        );
        assert.equal(headers.get("idempotency-key"), "same-request");
        const parsed = await new Response(init?.body, { headers }).formData();
        const file = parsed.get("file") as File;
        assert.deepEqual(
          new Uint8Array(await file.arrayBuffer()),
          new Uint8Array([1, 2, 3]),
        );
        return Response.json({ accepted: true }, { status: 201 });
      },
    },
  );
  assert.equal(response.status, 201);
});

test("audio ranges stream unchanged and remain uncached", async () => {
  const response = await proxyApiRequest(
    new Request(url, { headers: { Range: "bytes=0-2" } }),
    "hr",
    ["answers", "id", "audio"],
    {
      origin,
      fetcher: async (_, init) => {
        assert.equal(new Headers(init?.headers).get("range"), "bytes=0-2");
        return new Response(new Uint8Array([1, 2, 3]), {
          status: 206,
          headers: {
            "Content-Type": "audio/wav",
            "Content-Range": "bytes 0-2/100",
            "Accept-Ranges": "bytes",
            "Content-Length": "3",
          },
        });
      },
    },
  );
  assert.equal(response.status, 206);
  assert.equal(response.headers.get("content-range"), "bytes 0-2/100");
  assert.equal(response.headers.get("content-type"), "audio/wav");
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(
    new Uint8Array(await response.arrayBuffer()),
    new Uint8Array([1, 2, 3]),
  );
});

test("logout preserves an empty 204 response", async () => {
  const response = await proxyApiRequest(
    new Request(url, { method: "DELETE" }),
    "hr",
    ["session"],
    { origin, fetcher: async () => new Response(null, { status: 204 }) },
  );
  assert.equal(response.status, 204);
  assert.equal(await response.text(), "");
});

test("proxy cannot target other services or escape its API prefix", async () => {
  for (const [area, path] of [
    ["other", ["secret"]],
    ["hr", ["..", "secret"]],
    ["hr", ["a/b"]],
    ["hr", ["a\\b"]],
  ] as [string, string[]][]) {
    const response = await proxyApiRequest(new Request(url), area, path, {
      origin,
      fetcher: async () => {
        throw new Error("must not fetch");
      },
    });
    assert.equal(response.status, 404);
  }
});

test("configuration errors return a safe service-unavailable response", async () => {
  const response = await proxyApiRequest(new Request(url), "hr", ["session"], {
    origin: "file:///private/path",
  });
  assert.equal(response.status, 503);
  assert.equal((await response.json()).detail, API_UNAVAILABLE_MESSAGE);
});
