import { z } from "zod";
import { API_UNAVAILABLE_MESSAGE } from "./service-errors";
const id = z.string().uuid();
export const userSchema = z.object({ id, email: z.string(), name: z.string() });
export const sessionSchema = z.object({
  token: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
  token_type: z.literal("bearer"),
  expires_at: z.string(),
  user: userSchema,
  authentication: z.literal("demo"),
});
export const roleSchema = z.object({ id, name: z.string() });
const candidate = z.object({
  id,
  name: z.string(),
  email: z.string(),
  source_id: z.string().nullable(),
});
export const applicationSchema = z.object({
  id,
  candidate,
  interview_id: id,
  answered_count: z.number().int(),
  total_questions: z.number().int(),
  complete: z.boolean(),
});
export const jobSchema = z.object({
  id,
  answer_id: id,
  status: z.enum(["queued", "scored", "failed", "needs a person"]),
  attempts: z.number().int(),
  max_attempts: z.number().int(),
  retryable: z.boolean(),
  retry_at: z.string().nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  review_reason: z.string().nullable(),
});
const overrideSchema = z.object({
  id,
  actor_id: id,
  score: z.number().int().min(1).max(4),
  reason: z.string(),
  created_at: z.string(),
});
export const answerSchema = z.object({
  id,
  source_id: z.string().nullable(),
  is_current: z.boolean(),
  input_kind: z.enum(["text", "audio", "missing"]),
  text: z.string().nullable(),
  audio_url: z
    .string()
    .nullable()
    .refine(
      (value) =>
        value === null || /^\/hr\/answers\/[0-9a-f-]{36}\/audio$/.test(value),
    ),
  audio_mime_type: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  submitted_at: z.string(),
  source_submitted_at: z.string().nullable(),
  job: jobSchema.nullable(),
  suggestion: z
    .object({
      score: z.number().int().min(1).max(4),
      reason: z.string(),
      model: z.string(),
      rubric_version: z.string(),
      prompt_version: z.string(),
      created_at: z.string(),
    })
    .nullable(),
  overrides: z.array(overrideSchema),
  effective_score: z.number().int().min(1).max(4).nullable(),
  effective_score_source: z.enum(["hr", "model"]).nullable(),
});
export const reviewSchema = z.object({
  application: applicationSchema,
  questions: z.array(
    z.object({
      id,
      number: z.number().int(),
      prompt: z.string(),
      rubric_version: z.string(),
      rubric: z.record(z.string(), z.string()),
      revisions: z.array(answerSchema),
    }),
  ),
});
export type Role = z.infer<typeof roleSchema>;
export type Application = z.infer<typeof applicationSchema>;
export type Review = z.infer<typeof reviewSchema>;
export type Answer = z.infer<typeof answerSchema>;
export type Job = z.infer<typeof jobSchema>;
export type HRSession = z.infer<typeof sessionSchema>;
export class HRError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export class HRApi {
  constructor(
    private token = "",
    private fetcher: typeof fetch = (...args) => fetch(...args),
  ) {}
  private async request(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    let response: Response;
    try {
      response = await this.fetcher(`/api/hr${path}`, {
        ...init,
        headers,
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        signal: AbortSignal.timeout(30000),
      });
    } catch {
      throw new HRError(
        0,
        "Could not reach the server. Check your connection and try again.",
      );
    }
    if (!response.ok) {
      let detail = [502, 503, 504].includes(response.status)
        ? API_UNAVAILABLE_MESSAGE
        : "Request failed. Please try again.";
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {}
      throw new HRError(response.status, detail);
    }
    return response;
  }
  private async json<T>(
    path: string,
    schema: z.ZodType<T>,
    init?: RequestInit,
  ): Promise<T> {
    const response = await this.request(path, init);
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new HRError(502, "The server returned an unexpected response.");
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success)
      throw new HRError(502, "The server returned an unexpected response.");
    return parsed.data;
  }
  login(email: string, password: string) {
    return this.json("/session", sessionSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  }
  async logout() {
    await this.request("/session", { method: "DELETE" });
  }
  roles() {
    return this.json("/roles", z.array(roleSchema));
  }
  applications(roleId: string, offset = 0) {
    return this.json(
      `/roles/${encodeURIComponent(roleId)}/candidates?limit=50&offset=${offset}`,
      z.array(applicationSchema),
    );
  }
  review(applicationId: string) {
    return this.json(
      `/applications/${encodeURIComponent(applicationId)}`,
      reviewSchema,
    );
  }
  override(answerId: string, score: number, reason: string) {
    return this.json(
      `/answers/${encodeURIComponent(answerId)}/overrides`,
      overrideSchema,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score, reason }),
      },
    );
  }
  retry(jobId: string) {
    return this.json(
      `/jobs/${encodeURIComponent(jobId)}/retry`,
      z.object({ requeued: z.boolean(), job: jobSchema }),
      { method: "POST" },
    );
  }
  jobs(offset = 0) {
    return this.json(`/jobs?limit=50&offset=${offset}`, z.array(jobSchema));
  }
  async audio(answerId: string) {
    const response = await this.request(
      `/answers/${encodeURIComponent(answerId)}/audio`,
    );
    if (!/^audio\//.test(response.headers.get("content-type") || ""))
      throw new HRError(502, "Unexpected audio response.");
    return response.blob();
  }
}
