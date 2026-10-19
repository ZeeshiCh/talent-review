import { z } from "zod";
import { API_UNAVAILABLE_MESSAGE } from "./service-errors";

const receiptSchema = z
  .object({
    accepted: z.literal(true),
    receipt: z.uuid(),
    question_id: z.uuid(),
    input_kind: z.enum(["text", "audio"]),
    submitted_at: z.iso.datetime({ offset: true }),
  })
  .strict();
const questionSchema = z
  .object({
    id: z.uuid(),
    number: z.number().int().min(1).max(6),
    prompt: z.string().min(1),
  })
  .strict();
const progressSchema = z
  .object({
    total_questions: z.literal(6),
    answered_count: z.number().int().min(0).max(6),
    complete: z.boolean(),
    next_question_id: z.uuid().nullable(),
    questions: z
      .array(
        z
          .object({
            question_id: z.uuid(),
            answered: z.boolean(),
            receipt: receiptSchema.nullable(),
          })
          .strict(),
      )
      .length(6),
  })
  .strict();
const interviewSchema = z
  .object({
    title: z.string(),
    role: z.string(),
    questions: z.array(questionSchema).length(6),
    progress: progressSchema,
  })
  .strict()
  .superRefine((data, ctx) => {
    const ids = new Set(data.questions.map((q) => q.id));
    const answered = data.progress.questions.filter((q) => q.answered);
    const next =
      data.progress.questions.find((q) => !q.answered)?.question_id ?? null;
    if (
      ids.size !== 6 ||
      new Set(data.progress.questions.map((q) => q.question_id)).size !== 6 ||
      data.questions.some(
        (q, i) =>
          q.number !== i + 1 || data.progress.questions[i].question_id !== q.id,
      ) ||
      data.progress.questions.some(
        (q) =>
          !ids.has(q.question_id) ||
          q.answered !== (q.receipt !== null) ||
          (q.receipt && q.receipt.question_id !== q.question_id),
      ) ||
      answered.length !== data.progress.answered_count ||
      next !== data.progress.next_question_id ||
      data.progress.complete !== (answered.length === 6)
    ) {
      ctx.addIssue({
        code: "custom",
        message: "Interview progress is inconsistent",
      });
    }
  });

export type Receipt = z.infer<typeof receiptSchema>;
export type Interview = z.infer<typeof interviewSchema>;
export type Question = Interview["questions"][number];
export const MAX_AUDIO_BYTES = 20 * 1024 * 1024;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
  get retryable() {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }
}

export function personalToken(fragment: string): string | null {
  const tokens = new URLSearchParams(fragment.replace(/^#/, "")).getAll(
    "token",
  );
  return tokens.length === 1 && /^[A-Za-z0-9_-]{43}$/.test(tokens[0])
    ? tokens[0]
    : null;
}

export type Submission =
  | { questionId: string; kind: "text"; text: string }
  | { questionId: string; kind: "audio"; file: File };
export class SubmissionKeys {
  private previous: { submission: Submission; key: string } | null = null;
  for(submission: Submission): string {
    const previous = this.previous;
    const old = previous?.submission;
    if (
      previous &&
      old &&
      old.questionId === submission.questionId &&
      ((old.kind === "text" &&
        submission.kind === "text" &&
        old.text === submission.text) ||
        (old.kind === "audio" &&
          submission.kind === "audio" &&
          old.file === submission.file))
    )
      return previous.key;
    const key = crypto.randomUUID();
    this.previous = { submission, key };
    return key;
  }
  clear() {
    this.previous = null;
  }
}

export class CandidateApi {
  constructor(
    private readonly token: string,
    private readonly baseUrl = "/api",
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  private async request<T>(
    path: string,
    schema: z.ZodType<T>,
    init: RequestInit = {},
  ): Promise<T> {
    const controller = new AbortController();
    const signal = init.signal;
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timeout = setTimeout(abort, 30000);
    try {
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${this.token}`);
      headers.set("Accept", "application/json");
      const fetcher = this.fetcher; // Native browser fetch must not receive this class as its receiver.
      const response = await fetcher(this.baseUrl.replace(/\/$/, "") + path, {
        ...init,
        headers,
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        let detail = [502, 503, 504].includes(response.status)
          ? API_UNAVAILABLE_MESSAGE
          : "We couldn’t save your answer. Please try again.";
        if (
          typeof data === "object" &&
          data !== null &&
          "detail" in data &&
          typeof data.detail === "string"
        )
          detail = data.detail;
        if (response.status === 401)
          detail =
            "This personal link is invalid or has expired. Ask HR for a new link.";
        if (response.status === 403)
          detail = "This interview is unavailable. Please contact HR.";
        if (response.status === 422)
          detail = "Check your answer or audio file and try again.";
        throw new ApiError(response.status, detail);
      }
      const parsed = schema.safeParse(data);
      if (!parsed.success)
        throw new ApiError(
          502,
          "We couldn’t read the interview response. Refresh your saved progress.",
        );
      return parsed.data;
    } catch (error) {
      if (signal?.aborted)
        throw new DOMException("Request cancelled", "AbortError");
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        0,
        "Connection interrupted. Retry the same answer or check your saved progress.",
      );
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
    }
  }

  interview(signal?: AbortSignal): Promise<Interview> {
    return this.request("/candidate/interview", interviewSchema, { signal });
  }
  submit(
    submission: Submission,
    key: string,
    signal?: AbortSignal,
  ): Promise<Receipt> {
    const headers = new Headers({ "Idempotency-Key": key });
    let body: BodyInit;
    if (submission.kind === "text") {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify({ text: submission.text });
    } else {
      const form = new FormData();
      form.set("file", submission.file);
      body = form; // Browser supplies the multipart boundary.
    }
    return this.request(
      `/candidate/questions/${encodeURIComponent(submission.questionId)}/${submission.kind === "text" ? "answer" : "audio"}`,
      receiptSchema,
      { method: "POST", headers, body, signal },
    );
  }
}
