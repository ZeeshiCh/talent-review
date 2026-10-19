# Architecture and stack

## Stack choices

| Layer                 | Technology                      | Reason                                                                     |
| --------------------- | ------------------------------- | -------------------------------------------------------------------------- |
| Web                   | Next.js App Router + TypeScript | Candidate and HR interfaces with typed components                          |
| API                   | FastAPI + Pydantic              | Python-owned JSON API and request/response validation                      |
| ORM                   | SQLAlchemy 2                    | Explicit transactions, relational constraints, and worker-safe persistence |
| Driver                | psycopg 3                       | PostgreSQL connection support                                              |
| Migrations            | Alembic                         | Versioned, reviewable schema changes                                       |
| Database              | PostgreSQL 17                   | Durable records and transactional concurrency control                      |
| Background processing | Separate Python worker process  | Durable database job queue without another service                         |
| Tooling               | npm workspaces + uv             | One repository with independent web/Python lockfiles                       |

## Repository layout

```text
apps/web/src/app/             Next.js routes, layouts, and styles
apps/api/src/talent_api/      FastAPI application, settings, ORM, and services
apps/api/migrations/          Alembic environment and migrations
apps/api/tests/               Backend tests
compose.yaml                 Local PostgreSQL service
README.md                    Project overview
docs/                        Five supporting documents
```

Current backend modules are `main.py`, `config.py`, `db.py`, `models.py`, `scoring.py`, `verify_scoring.py`, `import_pack.py`, and `worker.py`. Routes/services/worker modules will be introduced as features require them. The web now has a public landing page and a complete candidate interview flow.

## Components and ownership

One monorepo contains a Next.js frontend and Python FastAPI service plus a separate worker process. PostgreSQL stores domain records and durable jobs; local private storage holds audio. This is a single-machine demonstration architecture. The API is the only authority for permissions and business rules. Next.js renders separate candidate and HR views and polls for job updates.

## Data model

Roles have interviews; interviews contain six ordered, rubric-versioned questions. Candidates have scoped invitations. Answers belong to a candidate and question and contain text or a private audio reference. Each accepted answer has at most one scoring job and one model suggestion. HR overrides are separate audited records with actor, reason, and timestamp. The displayed effective score is the latest HR override, otherwise the suggestion. Original model output is never overwritten by HR.

## API

Candidate endpoints expose interview questions, submission receipts, and resume progress only. HR endpoints provide sign-in, role/candidate review, job retry, authenticated audio access, and score overrides. Candidate bearer tokens cannot authorize HR endpoints. Separate response schemas prevent accidental grade leakage.

## Submission to score

Within a transaction, validate the invitation and question, accept an answer once, and enqueue its durable job. Return a receipt after commit. The worker claims the job with a lease, sends the question, rubric, and untrusted answer to a real model, validates structured output, and stores one suggestion transactionally. HR sees queued, scored, failed, or needs a person. Audio goes directly to needs a person because transcription is excluded. Expired worker leases can be recovered.

## Reliability and tradeoffs

Unique constraints enforce idempotency. A provider call may be repeated after a crash; only one accepted score can be persisted. Bound provider timeouts and retries; explicit failure never becomes a low score. Treat candidate text as untrusted data and test instruction attacks; prompting cannot guarantee immunity to every attack. Suspicious or invalid results require human review.

## Not built

Production authentication, distributed deployment, email delivery, audio transcription, ranking, and automated decisions. PostgreSQL and private local files keep setup small within twelve hours. A production system would need managed storage, stronger identity, and operational controls.

## Persistent tables

- roles, candidates, interviews, questions (ordered, four rubric text levels and rubric version).
- applications: one candidate/interview participation record; a candidate may apply to multiple roles.
- invitations: candidate/interview scope, hashed token, expiry.
- answers: candidate, question, input kind, text/audio reference, content hash, receipt, submission time.
- submission_keys: invitation scope, idempotency key, payload hash, answer ID.
- scoring_jobs: unique answer ID, public status, attempts, lease owner/expiry, safe error, review reason.
- suggestions: unique answer ID, integer score 1–4, reason, model identifier, rubric/prompt version, timestamp.
- overrides: answer ID, score 1–4, nonblank reason, HR actor, timestamp.
- hr_users: stable HR actor identity and active flag; no production password authentication yet.
- hr_sessions: HR actor, hashed session token, expiry, and revocation.

Initial candidate UI scope: one accepted current answer per candidate/question. A later different candidate payload receives 409; no editing/versioning UI. Imported historical revisions are a separate supported path: preserve both A022 and A023 for C2052/Q3 and designate A023 as current, ordered by source submission date and source ID. Enforce one current answer per candidate/question rather than uniqueness across all historical answer rows. Each revision has its own source ID and at most one job/suggestion. HR sees the accepted receipt and effective score. Exact duplicate content with a new submission key returns the original receipt. Database constraints, not preflight checks alone, resolve races. Do not deduplicate across candidates or questions.

## Candidate routes — candidate token required

- GET /candidate/interview: ordered public question data and persisted progress; no rubrics, grades, reasons, or job details.
- GET /candidate/questions/{id}: one public question scoped to the bearer invitation.
- GET /candidate/progress: persisted accepted receipts and the first unanswered question.
- POST /candidate/questions/{id}/answer: text JSON with a required idempotency key.
- POST /candidate/questions/{id}/audio: multipart audio with a required idempotency key; receipt and accepted state only.

Resume selects the first unanswered question from persisted accepted answers; after six answers show completion. Do not depend on local storage for correctness.

## HR routes — HR session required

- POST /hr/session and DELETE /hr/session: labelled demo authentication; expiring bearer token, stored only as SHA-256. GET reads the current HR identity.
- GET /hr/roles and GET /hr/roles/{id}/candidates.
- GET /hr/candidates/{id}: answers, suggestions, effective scores, override history, and public job states.
- GET /hr/answers/{id}/audio: authenticated file stream.
- POST /hr/answers/{id}/override: score and required reason.
- POST /hr/jobs/{id}/retry: failed jobs only; atomic transition back to queued.

## Permissions and validation

Validate authorization on every API request. Invitation scope determines candidate identity; never trust candidate IDs from the browser. Keep uploads outside public/static directories, generate storage names, limit size and supported formats, and reject empty/invalid input. Keep rubric and scoring response fields out of candidate schemas. Redact tokens and model credentials from logs.

## Job contract

Public states are exactly queued, scored, failed, needs a person. Lease metadata represents an active attempt while public status remains queued. Claim jobs atomically; only the lease owner may finalize. Use bounded attempts and timeouts. Retry reuses the same job. Enforce one persisted suggestion per answer.

## Pack import

The pack has been inspected; see the roadmap for source details and edge cases. Preserve source identifiers and question mapping; make import repeatable using unique source IDs. Store audio as human-review records, queue the 29 nonempty transcripts, and flag empty A007 for human review without scoring. Preserve both supplied revisions while displaying which one counts. Source timestamps have no timezone offset; preserve their original representation and document any timezone assumption instead of silently treating them as UTC. Do not use HR reference scores as model inputs or seed model suggestions.

## OpenAI adapter implementation

`OpenAIScorer` calls the official OpenAI Responses API with Pydantic structured output, `store=False`, bounded retries and timeouts, and the configured model snapshot. It isolates trusted instructions from answer JSON, validates score/review consistency, and returns model/response IDs with prompt/rubric versions. Refusals require human review with no numeric score; invalid/incomplete outputs and provider failures raise safe typed errors. The worker now invokes this adapter outside transactions and atomically persists validated suggestions with the final job status. Live provider verification awaits the API key. The separate verification CLI makes an explicit live request only when invoked.

## Implemented database invariants

Migration `0002` adds the complete domain model while preserving the original roles table. The database contains 13 domain tables plus Alembic metadata. UUID primary keys and timezone-aware creation timestamps are used throughout. Source timestamps are separately retained as original strings because the pack supplies no timezone offset.

Composite foreign keys tie each answer's application and question to the same interview. Submission keys must reference an invitation and answer belonging to the same application; suggestions must reference the answer belonging to their job. A partial unique index permits at most one current answer per application/question, preserving older revisions. A scoped content hash prevents identical duplicate revisions. Source answer IDs and receipts are unique.

Jobs have one row per answer revision and fields for claim tokens, lease expiry, attempt counts, availability, and safe failure/review reasons. Checks enforce the public status vocabulary, paired lease fields, failed-job errors, and human-review reasons. Suggestions have one row per answer/job with score 1–4 and model/response/rubric/prompt metadata. Overrides retain actor, reason, score, and timestamp as separate rows; foreign keys prevent accidental deletion of referenced history.

Database constraints do not authenticate requests, expire tokens automatically, enforce exactly six populated questions, require every answer to have a job, guarantee a scored job has a suggestion, or enforce append-only history. Services must perform those operations and atomic state transitions. Questions/rubrics used for scoring should be treated as immutable versions. Audio path and MIME fields are metadata; API upload handling still must validate actual files and restrict access. The ORM's job `updated_at` is refreshed on ORM updates; future raw worker SQL must set it explicitly.

## Data importer implementation

The importer validates the complete pack before writes, matches candidate identities from pipeline metadata, and runs one transaction under a PostgreSQL advisory lock. Imported role-specific interviews use deterministic dataset IDs; existing source rows must match rather than being silently edited. Question rubrics are fingerprinted. Every answer revision gets one job: nonempty text is queued, audio and missing content need human review. Model calls and suggestion creation are excluded from import.

Each role has its own six question rows (30 in this pack). Only candidates with supplied answers are imported. All historical revisions are retained and exactly one current imported revision is selected per application/question by parsed source date and source ID. Switching current revisions clears the previous partial-index entry before selecting the new revision. Unmanaged/live submissions in a slot cause an explicit conflict; reimport does not replace them. Future candidate submission services must lock the application record when changing answer slots.

Content-addressed audio files are written atomically with private permissions and byte-level checksum verification. The database and filesystem do not share a transaction: an aborted import may leave an unreferenced immutable blob, but no partial database state. The read-only verification command checks question/rubric content, candidate identity, source mappings, timestamps, payloads, current revisions, jobs, and audio bytes. Existing job outcomes, suggestions, and HR audit records are never reset. Import does not issue invitation tokens or mark partial interviews complete.

## Background worker implementation

`worker.py` is a separate process using the existing database job table. It claims one ready queued job or due retry under a row lock with `SKIP LOCKED`, records a fresh lease token/expiry, increments the lifetime attempt count, and commits before any provider call. Reference: https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE

The public status remains queued during processing; claim metadata indicates ownership. A second transaction finalizes only if status, answer ID, token, and lease expiry still match. Suggestion insertion and the scored transition are atomic. Database uniqueness prevents duplicate persisted scores; provider calls may repeat after crashes or lease expiry, so this is not an exactly-once provider-call guarantee.

Migration `0003` adds `retryable` and `retry_at`. A transient failure stays failed while awaiting exponential backoff; claim clears safe error fields only when a retry actually begins. Maximum attempts are bounded. Lease recovery consumes the same attempt budget; an exhausted abandoned claim becomes failed. Explicit maintenance retry locks the failed job, reuses its ID, clears stale errors/leases, and grants a new bounded budget without resetting lifetime attempts. Repeated/concurrent retry on an already queued job is a no-op. Previous error messages are not an attempt-history audit log; only the latest failure and lifetime count are retained.

The local status/retry CLI is for trusted development maintenance. No unauthenticated HTTP endpoints were added. HR HTTP routes authenticate and authorize in the same transaction before invoking the shared row-locked retry service. Suggestions remain immutable to normal retry flow; scored and human-review jobs cannot be explicitly retried through this command. Human review stores a reason and no numeric suggestion. Questions and answer revisions must remain immutable while in flight.

The poller can run continuously, attempt one job, or drain currently ready jobs. Drain does not wait for a future retry date; run continuously to handle scheduled retries. Provider timeouts and SDK retries are bounded, and startup checks that the configured lease exceeds that request budget. No heartbeat is implemented: responses arriving after lease expiry are discarded and the job is recovered. Logs expose only job IDs and safe outcome states. DB outages terminate the worker safely; unfinalized claims recover after lease expiry on restart.

## Candidate API implementation

Candidate routes, schemas, and transaction-owned services live in `candidate_routes.py`, `candidate_schemas.py`, and `candidate_service.py`. The staff-only `invite_candidate.py` CLI issues random 256-bit bearer tokens and stores only token hashes. Raw credentials are written once into ignored private files; there is no public issuance endpoint. Frontend personal links use a URL fragment, keeping credentials out of request URLs and referrers. The candidate frontend is implemented.

Each operation resolves invitation -> application -> interview in Python and validates expiry, revocation, and interview activation. Clients cannot choose a candidate/application ID. Question UUIDs are checked against the authorized interview; other interviews receive 404. Candidates get dedicated public response models with question text, accepted receipts, and progress only. No score, rubric, suggestion, job error/state, other candidate, invitation hash, or audio storage path is serialized. HR APIs independently enforce HRSession authentication and expose separate review contracts.

Submissions lock the application before checking idempotency/current answers, revalidate access, then atomically persist answer + job + submission key. A payload hash includes question scope; content hashes are compatible with the importer. Identical content returns the accepted receipt even under a different key, while changed submissions conflict. New submissions must target the first unanswered question. Imported missing-content placeholders may be superseded, retaining history and its original review job. Existing accepted text/audio is immutable. Resume excludes missing placeholders and is computed entirely from PostgreSQL.

A bounded ASGI request buffer caps JSON and multipart bodies before parsing. Audio is parsed using Mutagen and restricted to supported M4A/MP3/WAV streams with positive duration and matching declared types. This validates container/stream metadata, not a full malware scan or decode of every frame. Upload filenames are ignored; shared `storage.py` writes immutable content-addressed private blobs with atomic publication. Failed database writes may leave unreferenced private blobs for reuse; no database record commits partially. Candidate audio is flagged for HR review without invoking the scorer. Storage and database failures return safe retryable HTTP 503 responses.

The local Swagger verification uses explicitly labelled demo records separate from the imported pack. Browser reload clears Swagger authorization, but reusing the personal link recovers the same database progress. Production transport should use HTTPS; local development currently uses HTTP loopback.

## Candidate frontend implementation

The server-rendered interview route mounts a focused client component. It reads one token from the URL fragment, validates its shape, and loads the scoped interview through `CandidateApi`. Fragment changes cancel previous work and reset state only when the token changes. No token is copied to persistent browser storage. URLs/referrers sent to servers omit the fragment; generated links remain bearer credentials and should not be shared.

`candidate-api.ts` centralizes requests, timeouts/abort handling, safe errors, stable in-memory retry keys, and strict Zod response validation. Native fetch is called without binding it to the API-client instance. Browser requests use same-origin `/api/candidate/...`; Next server route handlers proxy only candidate/HR prefixes to FastAPI through server-only `API_ORIGIN`, defaulting to loopback port 8000. It forwards authorization and multipart bodies; it does not decide candidate permissions. The proxy streams file bodies without parsing multipart data; the Python streaming cap remains authoritative.

The view derives its current question and completed count from API progress. A successful POST's validated receipt produces immediate acknowledgment, and an explicit Continue action loads the next persisted question. Reloads restore server progress rather than resending local drafts. Text and audio are separate modes, with safe retry handling and a synchronous in-flight guard. Conflicts trigger a progress refresh. Draft text/file and request keys are deliberately memory-only; backend content/idempotency constraints keep resumed retries safe even after a reload.

Browser screens never request HR data, rubrics, suggestions, or scoring states. Completion lists accepted receipt metadata only. Metadata disables indexing and referrers; framing is denied on the interview page. Model keys and database credentials remain backend-only. Production deployment still requires HTTPS, the appropriate API origin, and operational controls.

## Implemented HR boundary

`hr_schemas.py` defines explicit review contracts and `hr_routes.py` owns authorization and transactional operations. Configured demo credentials bootstrap one active HR identity; sessions expire and can be revoked. Credentials are compared with constant-time comparison, missing configuration disables login, and session hashes never serialize. This local demo uses bearer headers rather than cookies; future browser clients must fetch authenticated audio as a blob. Production SSO, rate limiting, and deployment hardening are outside this local demonstration.

Role candidate lists expose application progress; application review includes every revision with an explicit current flag, four rubric levels, job state, original suggestion and audit history. Overrides serialize on the answer row and append actor/reason/score/server timestamp; latest override determines the effective score without changing suggestions or jobs. Private audio resolves inside configured upload storage and is served only after HR authorization. HR responses disable caching. Candidates, invitations and failed-job retries are available through protected routes. No email delivery or transcription is simulated. Existing schema supports these features without a migration.

## HR frontend

Next.js `/hr` provides a responsive sign-in and review workspace. Its strict Zod client uses the same-origin `/api/hr` server proxy; Python enforces all permissions. HR tokens are held only in React memory, cleared on logout/expiry/401, and never stored in browser persistence or URL parameters. Reloading returns to sign-in. Request timeouts and explicit refresh controls handle job updates without persistent polling. Changing roles/candidates ignores stale reads. Answer cards show current and historical revisions, rubric guides, original suggestions and effective scores, job failure/review reasons, and actor/timestamp/reason audit history. Overrides and retries guard in-flight clicks; Python retains final authority over duplicate job retries. Private audio is fetched with authorization and played from a temporary blob URL, revoked when the player unmounts. No model key is sent to the browser.

## Frontend composition and responsive behavior

Both routes compose focused view components. Candidate views separate progress, question input, audio/text modes, receipts and completion from their state hook. HR separates session/actions from read orchestration and uses independent loading flags for overlapping requests. Shared UI components provide consistent branding, headers, footers and accessible dropdown menus. Candidate CSS is grouped by layout, answer form and states; HR styles remain route-specific. Responsive verification uses real browser viewports at 320, 390, 768 and 1280 pixels, including overflow checks, accessible file-picker interaction and private audio loading.

## API transport failure boundary

A Node.js catch-all route handles only candidate and HR API prefixes. It builds URLs from server-owned API_ORIGIN, rejects path traversal, forwards a small header allowlist, and streams request/response bodies. Authentication and business rules remain in Python. Transport errors/timeouts return safe no-store 503 JSON with a retry hint instead of Next.js raw proxy errors. Upstream validation/authentication statuses and audio range headers pass through. No automatic write retries occur. The root development command uses concurrently to run web/API with labelled logs and shared shutdown behavior.

## Platform themes

The root layout wraps all pages in a small `next-themes` provider with a `data-theme` attribute, system appearance enabled and `talent-review.theme` as its browser preference key. Its initialization script applies the preference before hydration, preventing the default palette from flashing on reload. The theme control uses a hydration-safe mounted snapshot and segmented Light, Dark and System buttons. Compact mobile icons retain accessible labels. Shared Radix dropdowns provide keyboard navigation, selected checkmarks, collision-aware menus and consistent styling for role and score fields. The shared header exposes it on landing, candidate and HR pages.

`themes.css` owns semantic light/dark tokens for surfaces, text, borders, accents, status notices and focus indicators; route styles consume those tokens. Theme changes affect appearance only, not authentication, permissions or persisted interview data. Only a non-sensitive theme preference is saved in localStorage; invitation tokens and HR sessions retain their existing handling.
