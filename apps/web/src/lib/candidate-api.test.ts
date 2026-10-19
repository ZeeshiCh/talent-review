import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  ApiError,
  CandidateApi,
  SubmissionKeys,
  personalToken,
} from "./candidate-api.ts";

const token = "a".repeat(43);
const questions = Array.from({ length: 6 }, (_, i) => ({
  id: crypto.randomUUID(),
  number: i + 1,
  prompt: `Question ${i + 1}?`,
}));
const receipt = {
  accepted: true,
  receipt: crypto.randomUUID(),
  question_id: questions[0].id,
  input_kind: "text",
  submitted_at: "2026-10-15T09:00:00Z",
};
function interview() {
  return {
    title: "Interview",
    role: "Engineer",
    questions,
    progress: {
      total_questions: 6,
      answered_count: 0,
      complete: false,
      next_question_id: questions[0].id,
      questions: questions.map((q) => ({
        question_id: q.id,
        answered: false,
        receipt: null,
      })),
    },
  };
}
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });

for (const fragment of [
  "",
  "#token=short",
  `#token=${token}&token=${token}`,
  "#other=value",
  `#token=${"a".repeat(44)}`,
]) {
  test(`invalid personal fragment is rejected: ${fragment.slice(0, 20)}`, () =>
    assert.equal(personalToken(fragment), null));
}
test("valid fragment is read without query-string or storage access", () =>
  assert.equal(personalToken(`#token=${token}`), token));

test("API uses private authorization header, no cookies, and no cache", async () => {
  const fetcher: typeof fetch = async (url, init) => {
    assert.equal(String(url), "http://localhost:8000/candidate/interview");
    assert.ok(!String(url).includes(token));
    assert.equal(
      new Headers(init?.headers).get("Authorization"),
      `Bearer ${token}`,
    );
    assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.referrerPolicy, "no-referrer");
    return response(interview());
  };
  const result = await new CandidateApi(
    token,
    "http://localhost:8000/",
    fetcher,
  ).interview();
  assert.equal(result.progress.next_question_id, questions[0].id);
});

test("text retry sends the same idempotency key and unchanged content", async () => {
  const seen: string[] = [];
  const fetcher: typeof fetch = async (url, init) => {
    assert.ok(String(url).endsWith(`/questions/${questions[0].id}/answer`));
    assert.equal(
      new Headers(init?.headers).get("Content-Type"),
      "application/json",
    );
    assert.equal(init?.body, JSON.stringify({ text: "Evidence" }));
    seen.push(new Headers(init?.headers).get("Idempotency-Key") ?? "");
    return response(receipt, seen.length === 1 ? 201 : 200);
  };
  const keys = new SubmissionKeys();
  const submission = {
    questionId: questions[0].id,
    kind: "text" as const,
    text: "Evidence",
  };
  const api = new CandidateApi(token, "http://localhost:8000", fetcher);
  assert.deepEqual(await api.submit(submission, keys.for(submission)), receipt);
  await api.submit({ ...submission }, keys.for({ ...submission }));
  assert.equal(seen[0], seen[1]);
  assert.notEqual(keys.for({ ...submission, text: "Changed" }), seen[0]);
});

test("audio uploads use FormData and let the browser set the boundary", async () => {
  const file = new File([new Uint8Array([1, 2])], "answer.wav", {
    type: "audio/wav",
  });
  const submission = {
    kind: "audio" as const,
    questionId: questions[0].id,
    file,
  };
  const keys = new SubmissionKeys();
  assert.equal(keys.for(submission), keys.for({ ...submission }));
  const fetcher: typeof fetch = async (url, init) => {
    assert.ok(String(url).endsWith("/audio"));
    assert.equal(new Headers(init?.headers).get("Content-Type"), null);
    assert.ok(init?.body instanceof FormData);
    assert.equal(init.body.get("file"), file);
    return response({ ...receipt, input_kind: "audio" }, 201);
  };
  const saved = await new CandidateApi(
    token,
    "http://localhost:8000",
    fetcher,
  ).submit(submission, keys.for(submission));
  assert.equal(saved.input_kind, "audio");
});

for (const status of [401, 403, 409, 413, 415, 422, 503]) {
  test(`HTTP ${status} is not mistaken for acceptance`, async () => {
    const fetcher: typeof fetch = async () =>
      response({ detail: "Safe server error" }, status);
    await assert.rejects(
      () =>
        new CandidateApi(token, "http://localhost:8000", fetcher).interview(),
      (error: unknown) => error instanceof ApiError && error.status === status,
    );
  });
}

test("network interruption leaves a retryable error and stable retry key", async () => {
  const fetcher: typeof fetch = async () => {
    throw new TypeError("private connection info");
  };
  const keys = new SubmissionKeys();
  const submission = {
    kind: "text" as const,
    text: "Evidence",
    questionId: questions[0].id,
  };
  const key = keys.for(submission);
  await assert.rejects(
    () =>
      new CandidateApi(token, "http://localhost:8000", fetcher).submit(
        submission,
        key,
      ),
    (error: unknown) =>
      error instanceof ApiError &&
      error.retryable &&
      !error.message.includes("private connection"),
  );
  assert.equal(keys.for(submission), key);
});

test("malformed or sensitive response fields fail the public response boundary", async () => {
  const invalid = [
    { ...interview(), score: 4 },
    { ...interview(), progress: { ...interview().progress, complete: true } },
    {
      ...interview(),
      progress: { ...interview().progress, answered_count: 1 },
    },
    { ...interview(), questions: [questions[0]] },
    {
      ...interview(),
      questions: questions.map((q) => ({ ...q, rubric: "private" })),
    },
  ];
  for (const data of invalid) {
    const fetcher: typeof fetch = async () => response(data);
    await assert.rejects(
      () =>
        new CandidateApi(token, "http://localhost:8000", fetcher).interview(),
      (error: unknown) => error instanceof ApiError && error.status === 502,
    );
  }
});

test("malformed acceptance never produces a receipt", async () => {
  const fetcher: typeof fetch = async () =>
    response({ ...receipt, accepted: false });
  await assert.rejects(
    () =>
      new CandidateApi(token, "http://localhost:8000", fetcher).submit(
        { kind: "text", questionId: questions[0].id, text: "Evidence" },
        "key",
      ),
    (error: unknown) => error instanceof ApiError && error.status === 502,
  );
});

test("native browser fetch is invoked without a class receiver", async () => {
  const fetcher: typeof fetch = async function (this: unknown) {
    assert.equal(this, undefined);
    return response(interview());
  };
  await new CandidateApi(token, "http://localhost:8000", fetcher).interview();
});

test("API outage displays a clear message without pretending an answer was accepted", async () => {
  const api = new CandidateApi(
    "a".repeat(43),
    "/api",
    async () => new Response("Bad Gateway", { status: 503 }),
  );
  await assert.rejects(
    api.interview(),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 503 &&
      error.retryable &&
      error.message.includes("API service is temporarily unavailable"),
  );
});
