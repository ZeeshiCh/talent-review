# Constraints and rules

## Product and stack

- Keep the project in a monorepo using Next.js + TypeScript, Python + FastAPI, SQLAlchemy + Alembic, and PostgreSQL. In-memory persistence is insufficient.
- HR makes decisions; model output is a suggestion. Overrides require an authenticated HR actor, a score from 1–4, and a nonblank reason.
- Use a real language model for working text scoring. Cached, recorded, or fixed responses are allowed only as labelled test fixtures, never as the running scorer.
- Clearly label any mocked sign-in, email, or transcription. Audio upload/storage and HR visibility are required; transcription is optional.
- Complete the required flow before optional features.

## Permissions and privacy

- Python enforces every permission, including direct API calls. Candidate invitation scope determines identity.
- Candidates must never receive grades, model reasons, rubrics, HR data, or other candidates' records.
- Store uploads privately and serve them through authenticated HR routes. Validate size, supported formats, and nonempty input; generate storage filenames.
- Never commit secrets, `.env`, dependencies, build output, private uploads, or local runtime data.

## Reliability

- An exact duplicate submission must not create a second answer revision, job, or persisted score. Use database uniqueness and atomic writes.
- The candidate UI accepts one current answer per candidate/question. Identical retries return its receipt; changed candidate content conflicts. Imported historical revisions must be preserved, with exactly one designated current answer. HR can identify which revision counts and its effective score.
- Scoring failures stay visible and retryable; they must never be represented as low scores.
- Public job statuses are exactly `queued`, `scored`, `failed`, and `needs a person`.
- Validate strict model output: integer score 1–4 and a bounded, nonempty reason. Never clamp or default malformed scores.
- Treat candidate text as untrusted content. Test injection attempts and route uncertain results to human review; schema validation alone does not prove semantic correctness.
- Use bounded timeouts/retries and lease-safe recovery. A repeated provider call after a crash may occur; only one accepted score may persist.
- Preserve original suggestions and audited overrides separately.
- Imported typed answers must use the live scoring path. Never feed HR reference scores into the scorer.

## Documentation and completion

Maintain exactly six primary documentation files: root README plus architecture, coding patterns, rules, roadmap, and workflow. Describe implemented behavior honestly. Mark pending and unverified work explicitly. Setup must be checked from a clean environment before it is declared complete.
