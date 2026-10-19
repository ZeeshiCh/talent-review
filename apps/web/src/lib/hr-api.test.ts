import test from "node:test";
import assert from "node:assert/strict";
import { HRApi, HRError, answerSchema } from "./hr-api";
const token = "a".repeat(43);
const uuid = "00000000-0000-4000-8000-000000000001";
function client(
  body: unknown,
  status = 200,
  inspect?: (url: string, init?: RequestInit) => void,
) {
  return new HRApi(token, async (input, init) => {
    inspect?.(String(input), init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
}
test("HR requests use the same-origin proxy and isolated authorization", async () => {
  const api = client([{ id: uuid, name: "Engineering" }], 200, (url, init) => {
    assert.equal(url, "/api/hr/roles");
    assert.equal(
      new Headers(init?.headers).get("Authorization"),
      "Bearer " + token,
    );
    assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.referrerPolicy, "no-referrer");
  });
  assert.equal((await api.roles())[0].name, "Engineering");
});
test("login uses JSON credentials and validates demo session", async () => {
  const api = client(
    {
      token,
      token_type: "bearer",
      expires_at: "2026-10-16T00:00:00Z",
      user: { id: uuid, email: "hr@example.test", name: "HR" },
      authentication: "demo",
    },
    200,
    (_, init) => {
      assert.deepEqual(JSON.parse(String(init?.body)), {
        email: "hr@example.test",
        password: "secret",
      });
      assert.equal(init?.method, "POST");
    },
  );
  assert.equal(
    (await api.login("hr@example.test", "secret")).authentication,
    "demo",
  );
});
test("unauthorized and conflict responses preserve HTTP status", async () => {
  for (const status of [401, 409])
    await assert.rejects(
      client({ detail: "Rejected" }, status).retry(uuid),
      (error: unknown) =>
        error instanceof HRError &&
        error.status === status &&
        error.message === "Rejected",
    );
});
test("invalid server contracts are rejected", async () => {
  await assert.rejects(
    client([{ id: uuid, name: 23 }]).roles(),
    (error: unknown) => error instanceof HRError && error.status === 502,
  );
});
test("override sends only score and reason", async () => {
  const api = client(
    {
      id: uuid,
      actor_id: uuid,
      score: 3,
      reason: "Evidence",
      created_at: "2026-10-15",
    },
    200,
    (url, init) => {
      assert.equal(url, `/api/hr/answers/${uuid}/overrides`);
      assert.deepEqual(JSON.parse(String(init?.body)), {
        score: 3,
        reason: "Evidence",
      });
    },
  );
  assert.equal((await api.override(uuid, 3, "Evidence")).score, 3);
});
test("audio uses an authorization header and returns a blob", async () => {
  const api = new HRApi(token, async (input, init) => {
    assert.equal(String(input), `/api/hr/answers/${uuid}/audio`);
    assert.equal(
      new Headers(init?.headers).get("Authorization"),
      "Bearer " + token,
    );
    return new Response(new Uint8Array([1, 2, 3]), {
      headers: { "Content-Type": "audio/wav" },
    });
  });
  assert.equal((await api.audio(uuid)).size, 3);
});
test("audio rejects unexpected content types", async () => {
  await assert.rejects(
    client({ html: "oops" }).audio(uuid),
    (error: unknown) => error instanceof HRError && error.status === 502,
  );
});
test("network failures are safe and retryable by the caller", async () => {
  const api = new HRApi(token, async () => {
    throw new Error("private details");
  });
  await assert.rejects(
    api.roles(),
    (error: unknown) =>
      error instanceof HRError &&
      error.status === 0 &&
      !error.message.includes("private"),
  );
});
test("answer contracts reject remote audio URLs and invalid scores", () => {
  assert.equal(
    answerSchema.safeParse({
      audio_url: "https://elsewhere.test/audio",
      effective_score: 9,
    }).success,
    false,
  );
});
test("retry preserves the existing job identity", async () => {
  const job = {
    id: uuid,
    answer_id: uuid,
    status: "queued",
    attempts: 3,
    max_attempts: 6,
    retryable: false,
    retry_at: null,
    error_code: null,
    error_message: null,
    review_reason: null,
  };
  const result = await client({ requeued: false, job }).retry(uuid);
  assert.equal(result.requeued, false);
  assert.equal(result.job.id, uuid);
});

test("non-JSON gateway failures display a service-unavailable message", async () => {
  const api = new HRApi(
    "",
    async () => new Response("Bad Gateway", { status: 503 }),
  );
  await assert.rejects(
    api.login("hr@example.test", "test"),
    (error: unknown) =>
      error instanceof HRError &&
      error.status === 503 &&
      error.message.includes("API service is temporarily unavailable"),
  );
});
