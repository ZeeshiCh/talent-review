# Roadmap and project progress

## Current progress

- [x] Six-file documentation structure.
- [x] Monorepo in `/Users/zeeshanch/Work/talent-review`.
- [x] Next.js + TypeScript foundation page.
- [x] FastAPI application and SQLAlchemy session/settings setup.
- [x] PostgreSQL Compose configuration and initial roles migration.
- [x] Full SQLAlchemy domain schema and Alembic migration `0002` applied and verified.
- [x] API liveness/readiness endpoints; safe database-failure response.
- [x] Dependency lockfiles, production build, TypeScript checks, and backend tests.
- [x] Start PostgreSQL, apply migrations, and verify live database readiness.
- [x] Inspect data pack questions, rubrics, answer formats, and edge cases.
- [x] Configure the OpenAI SDK client, model settings, strict scoring schema, and smoke-check command.
- [ ] Add OPENAI_API_KEY locally and verify a real scoring call.
- [x] Candidate API: scoped personal-link tokens, questions, text/audio receipts, duplicate prevention, and persisted resume progress.
- [x] Candidate Next.js personal-link interview screens, one-question flow, text/audio submission, receipts, and resume/completion.
- [x] Durable OpenAI worker with atomic claims/finalization, lease recovery, scheduled failure retries, and explicit retry command.
- [ ] Verify live OpenAI scoring after the API key is configured; process the supplied text answers.
- [x] HR backend: labelled demo sign-in, role/candidate review, score reasons, audited overrides, invitation operations, and job status/retry.
- [x] HR Next.js sign-in, role candidates, answer/revision review, effective scores, audited overrides and job retries.
- [x] Candidate private audio upload, media validation, size limits, and human-review jobs.
- [x] HR-authenticated private audio API.
- [x] HR frontend authenticated audio fetch and playback.
- [x] Repeatable data pack import, revision/duplicate handling, private audio copy, and PostgreSQL verification.
- [x] Permission, concurrency, crash-recovery, and end-to-end verification without live model access.
- [x] Fresh local setup verification and candidate/HR walkthrough without live model access.

Last verified: 2026-10-19. 60 frontend tests and 144 backend tests pass, including PostgreSQL permissions, duplicate/concurrency checks, lease/crash recovery and a candidate → worker → HR lifecycle regression. Formatting, lint, TypeScript and production build pass. A source-only clean copy installed locked dependencies, migrated an empty PostgreSQL database, imported and verified all 35 supplied answers, and passed `npm run verify`. Production frontend/proxy checks against its real API verified role review, private audio, personal-link progress, permission isolation and logout. No live OpenAI request was made; live scoring and its provider-specific walkthrough remain pending.

## Database setup verification

- Docker Compose runs PostgreSQL 17 on `127.0.0.1:5433`, mapped to container port 5432.
- Port 5433 avoids the existing database service on host port 5432.
- Local configuration, example environment, and backend defaults use the same project port.
- Alembic migrations `0001`–`0003` are applied; current revision is `0003 (head)`.
- Live public schema contains 13 domain tables plus `alembic_version`, 15 foreign keys, and 30 check constraints.
- `alembic check` reports no new upgrade operations.
- 24 opt-in PostgreSQL tests passed in an isolated rolled-back schema, including migration round trips and preservation of existing role data. No test records remain in the live application tables.
- Verified current-revision uniqueness, content/idempotency uniqueness, one job/suggestion per revision, scope foreign keys, score ranges, override reasons, and token/expiry validation.
- SQLAlchemy connects to the `hiring` database, and the API readiness check returns HTTP 200 with `{"status":"ready"}`.

## Data pack inspection

Inspected release `v1.1.0`, asset `business-systems-pack.zip`, downloaded from https://github.com/Growtrics/hiring-challenge-data/releases/download/v1.1.0/business-systems-pack.zip. The archive is retained under ignored `var/data-inspection/pack.zip`; extracted originals are under `var/data-inspection/extracted/`.

- Archive SHA-256: `1dc35f640c16ae29fc21153d97bda13fdab1a8925a3b3e809086b41fd7815d7c`.
- Six questions (`Q1`–`Q6`), each with four explicit grading levels; five roles.
- 35 answer JSON records across 18 candidates: 29 nonempty transcripts, one empty transcript (`A007`), and five audio-only records (`A031`–`A035`). All five referenced `.m4a` files exist.
- Answers carry `answer_id`, `candidate_id`, `role`, `question_id`, `submitted_at`, `duration_seconds`, and `transcript`; audio records also carry `audio_file`.
- Candidate/question `C2052/Q3` has two distinct submissions, `A022` and later `A023`. Preserve both revisions; make `A023` current. Exact retries must still be idempotent. A per-candidate/question uniqueness constraint on all answer records would lose supplied data.
- `A019` contains an instruction to award a 4. Treat it as untrusted answer content and include it in injection tests; never follow its scoring instruction.
- Import `A007` as `needs a person` with a missing-content reason, without a model call or invented low score. New empty candidate submissions should be rejected.
- The supplied records are partial interviews: 17 candidates have two records, one has one. Do not mark interviews complete just because all supplied records were imported.
- All 18 answer candidates appear in `pipeline_log.csv`; use it for names/emails and role association. Preserve source IDs. The ten HR reference scores are evaluation-only and must never enter scoring prompts.
- The pack describes a historical video/two-scorer process and a pass mark. The product remains text/audio with a model suggestion and HR review; do not add video, automatic advancement, or rejection logic.

## Data import verification

Source: `/Users/zeeshanch/Downloads/business-systems-pack`. Questions, README, and pipeline metadata match the previously inspected release. Source files were left unchanged.

| Record                                          | Verified count |
| ----------------------------------------------- | -------------: |
| Roles / role-specific interviews                |          5 / 5 |
| Question definitions / database question rows   |         6 / 30 |
| Candidates with supplied answers / applications |        18 / 18 |
| Answer revisions / current answers              |        35 / 34 |
| Superseded revisions                            |              1 |
| Text / empty / audio answers                    |     29 / 1 / 5 |
| Scoring jobs: queued / needs a person           |         29 / 6 |
| Stored model suggestions                        |              0 |

- `A022` remains superseded; later `A023` is current for `C2052/Q3`. Input file order does not select the current revision.
- Original source IDs, source timestamps, transcripts, question mappings, and rubric levels are retained and verified. Source timestamps have no timezone; they are stored as supplied without inventing one. Imported `submitted_at` records database acceptance; original historical dates remain in `source_submitted_at`.
- Five audio files are copied to ignored `var/uploads/imported-audio`, outside the web application, with content-addressed filenames and private permissions. Stored bytes match source SHA-256 hashes.
- `A007` and the audio answers have explicit human-review reasons and no invented scores. `A019` retains its injection text verbatim as untrusted content.
- Only the 18 candidates represented in the answer files were imported. The other pipeline candidates, historical outcomes, and reference grades are excluded. All 18 interviews remain partial; importing the supplied subset does not mark them complete.
- Reimport completed with zero inserts; database snapshots confirm IDs, receipts, all stored fields, and job states remain unchanged. Existing scores/failures are preserved by the importer.
- `--verify-only` succeeds without changing database rows or stored files. Concurrent imports serialize on a transaction-scoped advisory lock and create only one copy; database constraints remain the final duplicate guard.
- Tests verify source conflicts roll back all database writes, revisions work in reverse/incremental input order, missing/unsafe audio is rejected, and unrelated metadata/reference grades are not required by the scoring path.
- Import queues jobs but makes no model calls. The background worker is implemented; processing the imported text jobs awaits the API key. Candidate upload endpoints are implemented; candidate screens are implemented; HR frontend screens are implemented.

## Live scoring prerequisites

OpenAI is selected. The Python SDK client uses the Responses API with Pydantic structured outputs. Both `.env` and `.env.example` contain server-only `OPENAI_API_KEY` (blank placeholder), `OPENAI_MODEL=gpt-4.1-mini-2025-04-14`, `OPENAI_TIMEOUT_SECONDS=45`, `OPENAI_MAX_RETRIES=1`, and `OPENAI_MAX_OUTPUT_TOKENS=1000`. The model is configurable. No live call has been made; API key and account/model access remain unverified.

1. Add a server-only OpenAI API key with funded quota and model access to ignored `.env`; never put it in chat or frontend code.
2. Completed: official OpenAI Python SDK, typed settings with a secret key field, structured response validation, bounded SDK retries/timeouts, and safe failure classification. Tests use HTTP mocks; these are not live scoring evidence.
3. Provide the question, exact four-level rubric, and answer text to the model; omit identity, historical outcomes, CV tier, and reference grades. Keep candidate content separate from trusted instructions.
4. Require structured output and validate an integer score 1–4, a bounded nonempty explanation, and any human-review signal/reason before persistence. Record model and rubric/prompt versions.
5. Completed: worker claim/finalize/retry logic, unique persisted suggestions, and local job status/retry commands. HR HTTP status/retry routes and authorization are implemented and tested.
6. After adding the key, run `npm run verify:scoring` to verify one real request using supplied answer A001 and its rubric. The CLI is a smoke check only; it does not persist scores or run background jobs. Then verify the injection case and provider failure handling. Record successful evidence before checking off live model access.
7. Audio transcription is outside the initial scope; route the five audio records to `needs a person`. Keep reference grades out of working suggestions.

## Background worker verification

- Migration `0003` adds durable retry scheduling (`retryable`, `retry_at`), an index, and a database check tying automatic retries to failed jobs with remaining attempt budget. Alembic reports no schema drift.
- The worker uses PostgreSQL row locks with `SKIP LOCKED` to claim jobs, commits the claim, and calls OpenAI outside the database transaction. Leased jobs remain publicly `queued`.
- Finalization checks the claim token and unexpired lease under a row lock; suggestion insertion and the `scored` state commit atomically. Expired/stale workers cannot store results or overwrite newer outcomes.
- Transient provider errors remain visible as `failed`, with bounded exponential backoff and a retry date. Invalid outputs, access/configuration errors, unexpected scorer failures, and exhausted budgets remain failed for explicit retry. Failures never create low scores.
- Crashed workers' expired leases can be reclaimed. An exhausted final lease becomes visibly failed. Explicit retries reuse the job, preserve the lifetime attempt count, and grant one fresh bounded budget; repeated/concurrent retry requests do not extend it twice.
- Model refusals and review-required output produce `needs a person`, without suggestions. Accidentally queued audio/empty input is also routed to human review without a model call.
- 16 worker tests passed in isolated PostgreSQL schemas. Coverage includes real competing connections, manual retry races, stale/expired owners, backoff, exhaustion, revalidation, review states, and rollback of both suggestion/status after an interrupted final transaction. Fake models are used only in tests.
- `npm run jobs:status` works against the live application database. The original pack retains 29 queued jobs and six needing a person. The completed Swagger/frontend demo adds four queued text jobs and two human-review audio jobs; current global totals are 33 queued, eight needing a person, zero suggestions, and no failed jobs. An attempted worker startup with the blank key failed safely before claiming or modifying any job.
- Live OpenAI scoring is **not verified**: `OPENAI_API_KEY` is still blank. No recorded/fake scores were written to the application database. HR pages and authorized retry endpoints are implemented.

## Candidate API and Swagger verification

Implemented endpoints:

- `GET /candidate/interview`: public question text, role, and persisted progress.
- `GET /candidate/questions/{question_id}`: one question scoped to the token's interview.
- `GET /candidate/progress`: durable receipts, answered count, completion flag, and first unanswered question.
- `POST /candidate/questions/{question_id}/answer`: JSON text with required `Idempotency-Key`.
- `POST /candidate/questions/{question_id}/audio`: multipart M4A, MP3, or WAV file with required `Idempotency-Key`.

Trusted local `candidate:invite` creates a cryptographically random personal token, stores only its SHA-256 hash in PostgreSQL, and saves the raw link details in an ignored private file. Candidate routes accept the token only as a bearer header, validate expiry/revocation/active interview on the server, and expose no identity-selection parameters or public invitation creation route. The Next.js screen reads the URL fragment and sends the token as a bearer header through its same-origin API proxy.

Submissions lock the application, recheck access after waiting, enforce the first-unanswered question, and commit the answer, stable receipt, idempotency mapping, and job together. Identical retries return HTTP 200 with the original receipt, including when a fresh request key is used. Changed content or reuse of a key for another payload/question returns HTTP 409. Imported empty placeholders remain unanswered and may be superseded by a valid submission; imported text/audio answers cannot be silently edited.

Audio is verified with a media parser, size capped, and saved under content-addressed filenames outside public directories. Request bodies are bounded before multipart parsing, including streamed requests without Content-Length. File names supplied by clients never determine the stored path. Audio returns an accepted receipt and creates a human-review job; no audio score is fabricated. All five supplied M4A files pass the upload media validator.

Swagger UI was exercised at `http://localhost:8000/docs` against two separately created synthetic demo applications:

- Missing token: HTTP 401.
- Valid personal token: interview/questions loaded with HTTP 200.
- Typed answer: HTTP 201; repeated request: HTTP 200 with the exact same receipt.
- Changed text under the same key: HTTP 409.
- Submission to another interview's question: HTTP 404.
- Real multipart WAV upload: HTTP 201; repeated upload: HTTP 200 with the same receipt.
- After a full Swagger reload and reauthorization, progress returned HTTP 200, two accepted answers, their original receipts, and question 3 as the next question.

At the end of the Swagger-only pass, database checks confirmed exactly two demo answers/jobs and two request-key rows after duplicate requests, with audio bytes matching the uploaded WAV. The frontend pass later completed this same synthetic demo application with six answers, six jobs, and six request-key rows. All original imported pack records and their job states still verify unchanged. Demo identities are labelled `Swagger Demo Candidate A/B`; link details are private under `var/swagger-verification.json`. These are additional synthetic development records, not model scoring evidence.

39 candidate API tests cover token classes (including HR-token rejection), cross-interview access, expiry/revocation, duplicate and conflicting parallel requests, resume/completion, empty imported answers, missing keys, invalid payloads, private audio, size/type validation, storage/database failures, transaction rollback, and exclusion of grades/rubrics/jobs/paths from responses. Swagger does not retain authorization across reloads. Candidate responses send `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.

HR routes now enforce HRSession authorization; candidate bearer tokens receive 401. HR pages are implemented. The candidate frontend is implemented and verified below. HR frontend playback is verified; live model scoring verification remains pending.

## Candidate frontend verification

- Implemented `/interview#token=...` in Next.js with a responsive interview layout, progress indicator, and exactly one question form at a time. The home page explains how to use an invitation.
- Personal tokens stay in the URL fragment for return/reload. The page does not put them in query strings, cookies, localStorage, or sessionStorage. They are sent only in authorization headers to the same-origin `/api/candidate/...` proxy. Referrers are disabled. No model credentials enter the frontend.
- The proxy forwards to FastAPI using server-only `API_ORIGIN`; Python remains responsible for permissions, question order, duplicate prevention, file validation, and persistence.
- Written answers and M4A/MP3/WAV uploads use the real API. Unchanged retries reuse a request key; a synchronous in-flight guard and disabled controls prevent double-click races. Browser response schemas validate public contracts and acceptance receipts.
- A confirmed API receipt is shown immediately; candidates explicitly continue to the next question. Progress checks/reloads use PostgreSQL. Unsubmitted drafts are held in page memory only and are not promised to survive reloads.
- Loading, missing-link, invalid/expired-link, network failure, invalid upload, saved receipt, and complete-interview states are implemented. Errors preserve the current draft/file where possible. Conflicts refresh saved progress without changing previously accepted answers.
- Verified against the live API in the browser: reopened demo A at question 3 with two saved answers; typed/double-clicked a submission; reloaded to question 4; uploaded WAV and saw its receipt; invalid WAV was rejected at question 5 without advancing; switched to text and completed questions 5/6; reloaded to a persisted six-answer completion screen.
- Verified a small-screen layout at a 390-pixel breakpoint, plus missing/unknown personal-link states. Original pack candidates/revisions/jobs still verify unchanged.
- Database confirms demo A has exactly six distinct accepted answers, six jobs, and six request keys (four written and two audio). There are no double-click duplicates. The original 35 imported answers remain unchanged; no scores were fabricated.
- 20 frontend tests pass for token parsing, safe request headers, native fetch invocation, retry keys, multipart boundaries, HTTP/network failures, and malformed/private response rejection. TypeScript and production build pass.
- Browser verification used the production server because the sandbox denied Turbopack's macOS file-watcher stream. The production server is running on loopback port 3000. This does not indicate a failed build or an API failure.
- HR frontend work is verified; live OpenAI verification remains pending.

## Implementation milestones

| Milestone                    | Exit condition                                                                                                 |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Foundation and prerequisites | Both services run, PostgreSQL persists data, input formats are understood, and live model access is confirmed  |
| Candidate submissions        | Authorized text submission returns a durable receipt, reload resumes progress, and duplicate tests pass        |
| Background scoring           | A live answer is scored; invalid output and provider failures are visible and recoverable                      |
| HR review                    | HR can review candidates, inspect score reasons, and override scores with a reason; candidate access is denied |
| Audio answers                | Audio is stored privately, acknowledged to the candidate, and accessible to HR for review                      |
| Data import                  | Supplied answers are imported repeatably; typed answers use the live scoring path                              |
| Reliability verification     | Permission, concurrency, validation, retry, and recovery checks pass                                           |
| Setup and documentation      | Fresh setup succeeds using the README and workflow instructions                                                |
| End-to-end validation        | Candidate and HR flows work together, and documentation matches observed behavior                              |

## Scope priorities

Complete the required end-to-end flow before optional features. Prioritize permissions, persistence, duplicate prevention, and failure recovery over styling and convenience tooling. Keep the scorer connected to a real model and preserve explicit job states. Add optional features only after the required acceptance checks pass.

## Agent workflow

Give the coding agent one vertical slice at a time. Each request states the acceptance criteria, files it may change, and relevant contracts. Ask it to explain migrations, permissions, concurrency, and state transitions. Read the resulting diff, run focused checks, correct mistakes, and commit the verified slice. Keep commits small and preserve history. Do not bulk-generate the entire application and review it only at the end.

Suggested commit sequence: planning; runnable scaffold; candidate persistence; live scoring worker; HR review; audio and importer; reliability fixes; verified setup documentation. Order can change when integration findings require it.

## Backend completion verification

- HR demo login uses configured private credentials, expiring hashed bearer sessions, active-user checks and logout revocation. It is explicitly labelled mock authentication.
- Protected APIs cover roles, interviews, candidate creation/listing, role progress, application review with every answer revision, original suggestions and reasons, effective scores, append-only overrides, private audio, invitations, job inspection, and failed-job retries.
- Review marks the current revision and preserves historical revisions. Override identity comes from the session; score/reason validation rejects invalid requests. Failed jobs never acquire invented grades.
- 143 backend tests pass with PostgreSQL enabled, including 18 HR cases. Live API checks read five roles and 20 applications, verified private audio and anonymous rejection, and verified session revocation. Original job counts remain 33 queued, eight needing a person, zero scored/failed; no model suggestions were fabricated.
- Swagger and ReDoc render the complete backend contracts with separate CandidateLink and HRSession authorization schemes. Existing tables support the HR backend without another migration.
- OpenAI key and live scoring verification remain pending by request. Production identity/deployment hardening and a clean-machine setup check are not declared complete.

## HR frontend verification

- Implemented `/hr` with clearly labelled demo sign-in, role candidate lists and progress, answer/rubric/revision review, original model reasons and effective scores, audited overrides, private audio playback, and job status/retry views.
- Same-origin HR proxy and validated client contracts connect the interface to FastAPI. Sessions stay in memory; logout/expiry clears access and reload requires sign-in. Audio uses authorized blob fetches with object URL cleanup. Explicit refresh reloads job and review state.
- Browser verification passed for sign-in, role/candidate review, double-click override protection, persisted effective score, audio metadata/playback, invalid-credential feedback, and logout. One labelled synthetic demo override was saved; no imported answer or model suggestion was changed.
- Failed-to-queued UI retry was verified with the production frontend and a temporary API backed by an isolated PostgreSQL schema. Double-click reused the job and granted one bounded budget. The verification schema/server were removed; the live queue remains 33 queued and eight needing a person, with zero model suggestions.
- 30 frontend client tests, TypeScript checking and production build pass. Existing 143 backend tests cover the API; supplied data still verifies unchanged. The verified frontend runs on loopback port 3002 because a previous local server occupies 3000.
- Live model scoring and clean-machine setup/end-to-end scoring verification remain pending. No live score is claimed from mocked test fixtures.

## HR component and dropdown refinement

- Replaced the 800-line HR workspace with a 69-line composition page, focused view components, and a separate session/data hook.
- Extracted candidate sidebar/review, answer card, score summary, audit history, override form, private audio, jobs, sign-in, header, and shared select components. View props expose only consumed fields.
- Moved HR-specific styles out of the global candidate stylesheet. Fixed clipped dropdown labels/arrows with a wider score field and reserved chevron spacing; native menu and keyboard behavior remain intact.
- TypeScript, production build, and all 30 frontend tests pass. Browser verification confirms role switching, persisted review, and score selection with an unclipped label/arrow. No new score or override was saved during this refinement.

## Full frontend component and responsive audit

- Candidate route is now a 28-line composition component. Extracted progress sidebar, state routing, question panel, answer form, text/audio inputs, receipt and completion components. Submission/token/draft handling lives in a cohesive interview hook.
- Shared brand/header/footer components keep landing, candidate and HR pages consistent. Candidate styling is separated into layout, answer-form and receipt/state styles rather than compressed global rules. Existing API modules retain their separate contract/transport responsibility.
- HR session/actions and review-data loading now use separate hooks. Independent loading flags prevent one completed request from enabling refresh while another is still pending; stale responses are ignored after navigation.
- Fixed duplicate visible audio pickers while retaining an accessible native file input and focus indication. Improved mobile field sizes, touch targets, narrow header spacing, long answer wrapping, icon sizing and missing-link spacing. Native select text and chevron spacing remain correct.
- Browser checks at 320, 390, 768 and 1280 pixels confirm no horizontal overflow on checked screens. Reviewed landing, missing/invalid invitations, candidate text/audio forms, receipts/completion, HR login, role/candidate review, override fields and job views.
- Against an isolated PostgreSQL schema, verified text double-click acceptance, invalid audio rejection, valid WAV receipt, reload/resume, all-six-answer completion after reload, HR override double-click producing one audit entry, authenticated audio metadata, failed-job retry and logout. No real model call or artificial model suggestion was used.
- Final production build and TypeScript checks pass; all 30 frontend client tests and 143 backend tests pass. Original pack verification remains unchanged. The temporary browser schema, upload directory and proxy are removed after the checks; the production frontend remains available on port 3002.

## Formatting and linting

- Configured root Prettier and ESLint for frontend, supported repository configuration and documentation; configured Ruff for Python source, migrations and tests. Tooling dependencies and lockfiles are updated.
- Added root format, format-check, lint, lint-fix and combined check commands, plus commands for each toolchain. Added EditorConfig and generated/private file exclusions.
- Applied repository-wide formatting and safe lint fixes, including Python import ordering and the missing HR effect dependency. Documented the narrow hook synchronization lint exception; permission/business logic is unchanged.
- Format-check, lint, TypeScript, 30 frontend tests, 143 backend tests and production build are verified after cleanup. Setup/workflow documentation includes the exact commands.

## Combined startup and API outage handling

- Added `npm run dev` to start the Next.js frontend on 3002 and FastAPI on 8000 together, with named logs and coordinated shutdown/failure handling. Individual commands remain available. Webpack polling avoids local watcher exhaustion.
- Replaced raw external rewrites with a restricted streaming server proxy. API connection failures and timeouts return safe HTTP 503 JSON with a readable retry message and privacy headers. No request credentials or backend exception details are exposed, and writes are not retried automatically.
- Shared client fallback handles non-JSON gateway errors. Existing API auth/validation statuses, multipart bodies, idempotency headers, audio bytes/ranges and 204 logout responses are preserved.
- WEB_ORIGIN default/example/local configuration matches port 3002 for personal links.
- 40 frontend/proxy tests pass. Browser/curl verification confirms the API-down sign-in message, candidate outage response, healthy proxy behavior and recovery after API restart. Combined startup/shutdown/restart and the full checks/build/backend suite are verified.

## Platform theme support

- Added Light, Dark and System appearance modes through a reusable provider and shared header selector. System follows device appearance; a non-sensitive browser preference persists across pages/reloads and synchronizes between tabs.
- Centralized semantic palette tokens and applied them throughout landing, candidate and HR screens, including cards, forms, progress, audio, focus and status/error states. No permission or authentication behavior changed.
- Added hydration-safe segmented theme buttons with compact accessible mobile icons. Replaced role and score dropdowns with reusable Radix menus, consistent icons, selected checkmarks, focus states and touch targets. Browser checks confirm reload/navigation persistence, System resolution, dark candidate upload/review screens, light mode and a 320px header without horizontal overflow.
- 60 frontend tests pass, including 20 palette contrast checks. Format/lint/TypeScript and production build pass. Theme verification makes no model call or answer/score changes.

## Final verification without live model access

- Added a cross-service PostgreSQL regression: duplicate candidate submission → visible provider failure → HR retry → one persisted test suggestion → audited override with original suggestion preserved → candidate resume/privacy → private audio → logout. Test data is rolled back; the working scorer remains OpenAI.
- Re-ran the full suite: 144 backend tests pass with PostgreSQL enabled. Fresh-copy `npm run verify` passes 60 frontend tests, 39 ordinary backend tests and 119 PostgreSQL/import checks (14 importer parser cases overlap), followed by the production build.
- Verified setup in a temporary source-only copy with no inherited `.env`, `node_modules`, `.venv`, `.next`, uploads or runtime data. `npm ci` and locked `uv sync` succeed; an empty dedicated PostgreSQL database migrates to `0003` with 14 total tables.
- The clean database imports 35 revisions across 18 candidates and five roles, with 34 current answers, 29 queued jobs and six needing a person; read-only verification passes and no suggestions are created.
- Started the clean production frontend and API together through the actual proxy boundary. Verified landing/HR responses, five roles, six-question review, private imported audio and anonymous rejection, invitation/progress, HR/candidate token isolation, session revocation, Swagger and ReDoc.
- `npm run db:up` now waits for PostgreSQL health. Added `npm test` for ordinary tests and `npm run verify` for the complete checks/build path. README includes direct setup/import/test/run instructions and current evidence.
- Clean local setup is verified on this macOS host with new dependencies and a new database; a separate physical machine or every OS was not tested. Production identity, email, deployment and optional transcription remain outside scope.

## Remaining: OpenAI key and live verification

Add the key to ignored root `.env` when ready. Run the real smoke request and injection case, start the worker to process supplied text answers, verify stored model suggestions/reasons and live provider failure/retry behavior, and walk through both areas with those live results. These are the only remaining in-scope checks; they are deliberately unverified until credentials are supplied.
