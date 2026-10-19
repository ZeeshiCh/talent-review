# Development workflow

Run commands from `/Users/zeeshanch/Work/talent-review` unless a step explicitly changes directory.

## Requirements

Node.js 20.9+, npm, Python 3.11+, uv, and Docker Desktop with its daemon running. These instructions assume macOS/Linux. The database credentials below are for local development only.

## Setup

Run from the repository root:

```sh
cp .env.example .env
npm ci
uv sync --project apps/api --locked
npm run db:up  # Waits for database health
npm run db:migrate
```

`npm run db:up` waits for the database health check before returning; `docker compose ps` confirms its state. The project uses host port 5433 (container port 5432) to coexist with other local PostgreSQL services. If host port 5433 is already used, change the Compose host port and `DATABASE_URL` together. Copying `.env` is only needed on first setup.

## Run

Start both services with one command from the repository root:

```sh
npm run dev
```

Web: http://localhost:3002. API documentation: http://localhost:8000/docs.
`concurrently` prefixes web/API logs and stops the sibling process if one fails. Ctrl+C stops both services. Stop any standalone process already using 3002/8000 before running the shared command. Development uses Webpack with one-second polling to avoid local file-watcher exhaustion. `npm run dev:web` and `npm run dev:api` remain available separately.

`GET /health` checks the API process; `GET /health/ready` checks PostgreSQL connectivity and returns 503 when unavailable. It does not validate migration state. CORS permits the configured local web origin.

## Verify

```sh
npm test             # Frontend + backend checks that do not require PostgreSQL
npm run test:db      # Permission, concurrency, recovery and database checks
npm run verify       # All checks above, formatting/lint/types and production build
```

The default backend tests do not require a database; PostgreSQL integration tests are skipped unless explicitly enabled. To check the real database after migrations, start the API and request `http://localhost:8000/health/ready`. Migrations create the full 13-table domain schema, plus `alembic_version`; data is loaded separately with the importer below.

## Migrations

```sh
cd apps/api
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Review generated migrations before applying them. Stop the database with `docker compose stop db`; its named volume retains data. Never commit `.env`, dependencies, uploads, or build output.

## Working on a feature

1. Read the project overview, architecture, coding patterns, and rules.
2. Select the next incomplete roadmap item and define its acceptance criteria.
3. Implement a small end-to-end slice; inspect generated code and migration changes.
4. Run relevant automated checks and manually verify the affected flow.
5. Update roadmap checkboxes with observed evidence and note any limitations.
6. Commit the reviewed change, preserving history and excluding secrets/generated output.

## Required verification as features are added

## Model scoring boundary

Use a real model adapter configured by environment. Supply the question and its grading guide, separate candidate text as untrusted data, and explicitly prohibit following instructions inside it. Require a strict response schema: integer score 1–4, bounded nonempty reason, and a human-review signal/reason. Reject extra fields, invalid JSON, booleans/floats as scores, missing reasons, and out-of-range values. Never clamp or default an invalid score to 1.

Valid review-required responses become needs a person, without an accepted score. Invalid output or exhausted provider errors become failed, with a safe visible reason and retry. Audio is needs a person with an explicit transcription-not-implemented reason. Test adversarial instructions; document that prompt isolation and schema checks reduce risk but do not prove universal immunity.

## Required automated checks

- Same idempotency key + same payload returns the same answer/job; changed payload returns conflict.
- Same content with a fresh key returns the accepted answer; concurrent requests persist one answer/job/suggestion.
- Candidate token cannot read HR endpoints, scores, other candidates, rubrics, or audio; candidate responses contain no sensitive fields.
- Progress survives API restart and page reload.
- Valid model response scores; malformed, missing, and out-of-range responses do not score.
- Provider failure remains failed; HR retry reuses the job; repeated retry cannot enqueue duplicate work.
- Worker crash/lease expiry permits recovery; a stale worker cannot overwrite a finalized result.
- Override requires HR auth, integer 1–4, and a nonblank reason; suggestion remains preserved.
- Audio upload persists privately, has a receipt, and appears to HR as needs a person.
- Import is repeatable and expected pack records map to correct questions.

Use fake model clients for deterministic tests; include explicit injection cases. Add a live smoke run using real credentials and real pack answers before claiming completion. Do not assert an exact score in a nondeterministic live smoke test.

## Manual walkthrough and clean setup

Use separate candidate and HR browser sessions. Demonstrate receipt, refresh, scoring, overrides, permissions, audio, and controlled provider failure/retry. Remove temporary failure switches afterward. Run documented setup in a fresh environment, backend checks, frontend type check, and production build. Inspect the diff and ensure no secrets, dependency folders, uploads, or build output are committed.

## OpenAI scoring client setup

The server uses the official OpenAI Python SDK and Responses API structured outputs:
https://developers.openai.com/api/docs/guides/structured-outputs

The selected configurable snapshot is documented at:
https://developers.openai.com/api/docs/models/gpt-4.1-mini

Add your real key only to the root ignored `.env`:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4.1-mini-2025-04-14
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=1
OPENAI_MAX_OUTPUT_TOKENS=1000
```

Do not overwrite an existing `.env` with the example. Restart the API/worker after changing settings. The API starts without a key; creating the scoring client without one fails with a safe configuration error. The key is a secret settings field and is never returned through an API.

After adding the key, explicitly run a live check (this makes a billable API request):

```sh
npm run verify:scoring
```

Default input is A001 from the inspected pack under ignored `var/data-inspection/extracted`. For another transcript or a separately extracted pack:

```sh
npm run verify:scoring -- --answer-id A019
npm run verify:scoring -- --pack-dir /absolute/path/to/extracted-pack
```

The command reads the matching question and all four rubric levels. It prints validated output, response/model IDs, and rubric/prompt versions. It never reads HR reference scores, persists a score, or starts a background job. A019 is the supplied injection case: inspect its reasoning against the rubric; a successful structured response alone does not demonstrate resistance to all injection attacks. Empty A007 and audio-only inputs are rejected before network access.

`npm run test:api` uses HTTP mocks for model tests and never spends API credits. Live model verification remains pending until an actual request succeeds. If uv cache access is restricted in an agent environment, set `UV_CACHE_DIR` to the project's ignored `var/uv-cache` when running commands.

## PostgreSQL schema checks

With PostgreSQL healthy and migrations applied, run:

```sh
npm run test:db
```

The database and importer checks create a randomly named schema inside a transaction and roll it back afterward. They exercise the real migrations, foreign keys, checks, indexes, historical answer revisions, idempotency constraints, and override audit records without inserting data into the public application tables. The tests require schema-creation privileges in the local development database.

Run the entire backend suite with database checks enabled:

```sh
RUN_DB_TESTS=1 npm run test:api
```

Inspect migration state and model drift:

```sh
cd apps/api
uv run alembic current
uv run alembic check
```

Expected revision is `0003 (head)`. Expected table count is 14 including `alembic_version`. Refresh the TablePlus connection to see new tables. Do not run downgrade commands on the application database to test reversibility; the integration test performs its migration round trip only inside the isolated test schema.

## Import the data pack

From the project root, with PostgreSQL running and migrations applied:

```sh
npm run data:import -- --pack-dir /Users/zeeshanch/Downloads/business-systems-pack
```

Use the extracted directory containing `questions.md`, `answers/`, and `pipeline_log.csv`. The importer uses pipeline metadata only for the identities of candidates represented in `answers/`; it does not import historical outcomes or reference scores. The source directory is read-only to the importer. For another machine, pass that machine's extracted pack location.

A reproducible source is the pinned release asset:
https://github.com/Growtrics/hiring-challenge-data/releases/download/v1.1.0/business-systems-pack.zip

To download a fresh copy without modifying the original Downloads folder:

```sh
mkdir -p var/data-pack
curl --fail --location https://github.com/Growtrics/hiring-challenge-data/releases/download/v1.1.0/business-systems-pack.zip --output var/data-pack/pack.zip
unzip -n var/data-pack/pack.zip -d var/data-pack/extracted
npm run data:import -- --pack-dir "$PWD/var/data-pack/extracted"
```

The inspected ZIP SHA-256 is `1dc35f640c16ae29fc21153d97bda13fdab1a8925a3b3e809086b41fd7815d7c`; compare using `shasum -a 256 var/data-pack/pack.zip` if downloading again.

Import prints created/reused counts and verifies persisted associations, all rubric levels, revisions, job existence, and audio checksums. Repeating the command preserves IDs, receipts, job statuses, and existing suggestions. Changed source records are rejected rather than overwritten. Duplicate content under a different source answer ID is an explicit conflict, because the current schema has no source-ID alias table; it is never silently dropped or scored twice.

The entire database import is one transaction. Audio is copied atomically into private, ignored `var/uploads/imported-audio`; failed database imports can leave harmless immutable blobs, which a subsequent import reuses. Do not change the audio storage location between reruns for an existing dataset. Deletion/cleanup of unused blobs is not implemented.

Read-only verification:

```sh
npm run data:import -- --pack-dir /Users/zeeshanch/Downloads/business-systems-pack --verify-only
```

Expected initial result: 5 roles, 5 interviews, 30 question rows, 18 candidates/applications, 35 revisions (34 current), 35 jobs (29 queued and six needing a person). Five audio files are copied. `A023` supersedes `A022`. There are no suggestions until the OpenAI key is configured and the background worker runs. Refresh TablePlus to inspect records.

Source historical timestamps are preserved as strings without assigning an unsupported timezone. For imported records, `submitted_at` records when the database accepted the import; use `source_submitted_at` for the original historical timestamp. Revisions are ordered by parsed source date and source ID, with incompatible mixed timezone formats rejected.

Importer tests are included in `npm run test:db`. The concurrent-import test uses a randomly named disposable test schema and removes only that schema afterward. No test changes the imported public application data.

## Background scoring worker and retries

Apply migrations before running the worker:

```sh
npm run db:migrate
```

Add the real `OPENAI_API_KEY` only in root `.env`. Startup fails before claiming work when it is blank. Never use fake keys or fake models to populate the application database.

After configuring the key, verify one real persisted score:

```sh
npm run worker -- --once
npm run jobs:status
```

The worker makes billable OpenAI requests. `--once` processes at most one ready claim; it may do no work if jobs are leased, finished, or waiting for retry. Confirm the job is scored and its suggestion has a real model/response ID and rubric-based reason. Human-review output is also a valid outcome but does not verify a numeric suggestion.

Run continuously in a separate terminal for background processing and scheduled retries:

```sh
npm run worker
```

Process only currently ready jobs and exit:

```sh
npm run worker -- --drain
```

Use `--max-jobs 5` to bound processing, or `--once --job-id UUID` to select a specific ready job. Drain stops when nothing is ready; it does not sleep until future retries become due. Ctrl+C stops polling; an interrupted provider call leaves a lease that another run can recover after expiry.

Inspect failures and explicitly retry one:

```sh
npm run jobs:status
npm run jobs:retry -- JOB_UUID
```

These are trusted local maintenance commands. HR HTTP permissions and operations are implemented; the HR UI is implemented at `/hr`. Explicit retry accepts only failed jobs; an already queued job is unchanged, and scored/human-review jobs are rejected. Job IDs, answer revisions, and suggestions are not duplicated. Lifetime attempts are preserved; a single new bounded attempt budget is granted. Fix invalid credentials or quota before retrying provider-access failures.

Worker environment defaults (already included in `.env.example` and local `.env`):

```dotenv
WORKER_LEASE_SECONDS=300
WORKER_POLL_SECONDS=2
WORKER_RETRY_BASE_SECONDS=10
WORKER_RETRY_MAX_SECONDS=300
WORKER_RETRY_ATTEMPTS=3
```

The final setting controls the budget granted by explicit retry; new imported jobs initially have the database default of three attempts. The worker validates that the lease exceeds `OPENAI_TIMEOUT_SECONDS * (OPENAI_MAX_RETRIES + 1)` plus a margin. Keep only the four documented public job states. Active leases are represented by fields, not a fifth processing status. Internal logs may report `lease_lost`; that is never stored as a public job status.

All worker tests use fake models inside isolated PostgreSQL schemas. They do not call OpenAI or change public application jobs:

```sh
npm run test:db
```

To verify failure/retry in a live walkthrough, use a dedicated disposable test candidate after those routes exist. Do not break credentials for the entire imported queue. Live verification of the current pack remains pending until the key is added.

## Candidate API and personal links

Swagger: http://localhost:8000/docs. The API must be running with `npm run dev:api`.

Find an application's UUID in TablePlus, then issue a scoped link from the project root:

```sh
npm run candidate:invite -- APPLICATION_UUID
```

An optional `--days 7` controls expiry (1–30 days). This is a trusted local command, not a public endpoint. Raw token/link details are saved to an owner-only JSON file under ignored `var/candidate-links/`; PostgreSQL stores only the hash. Treat the file as a credential. Open the generated `/interview#token=...` URL in the running Next.js app, or use the token in Swagger to test the API directly.

Swagger steps:

1. Open the private JSON locally, copy only `token`, click **Authorize**, paste it without the `Bearer` prefix, and apply credentials.
2. Execute `GET /candidate/interview`; copy `progress.next_question_id`.
3. Execute `GET /candidate/questions/{question_id}` to see the current question, or use its text from the interview response.
4. For text, execute `POST /candidate/questions/{question_id}/answer` with an `Idempotency-Key` such as `answer-q1-001` and JSON `{"text":"Your answer"}`.
5. For audio, use the separate `/audio` endpoint and choose a valid M4A, MP3, or WAV file. The default cap is 20 MiB (`CANDIDATE_MAX_AUDIO_BYTES=20971520`). Actual audio metadata and declared type are validated; naming a text file `.wav` is insufficient.
6. A first acceptance returns HTTP 201 with a receipt; identical retries return HTTP 200 and the same receipt. Reuse keys only for identical submissions. Changed content/key scope or submitting ahead of the current question returns HTTP 409.
7. Reload Swagger, reauthorize with the same token, and execute `GET /candidate/progress`. Receipts and the next unanswered question come from PostgreSQL, not browser state. Completed interviews return `complete=true` and no next question.

Audio is stored privately under ignored `var/uploads/candidate-audio` and flagged for human review. Candidates cannot fetch uploaded blobs through public URLs. HR can retrieve audio through authenticated `/hr/answers/{answer_id}/audio`. Authorization is intentionally not persisted by Swagger across reloads. Candidate responses disable caching and referrer forwarding.

The recorded local Swagger checks used two labelled synthetic demo candidates in addition to the imported 18. Demo A was subsequently completed through the candidate frontend and now has four text answers and two audio answers; demo B exists for scope-isolation checks. `var/swagger-verification.json` contains private demo link details and must never be committed. `var/swagger-audio.wav` is generated synthetic silence used for upload verification. Original pack candidates and their 35 revisions were not edited.

Candidate tests (including actual concurrent database connections) are part of:

```sh
npm run test:db
```

Do not expose the local invitation CLI or private files as public web routes. Candidate tokens are not HR credentials; HR authentication and authorization use separate HRSession bearer tokens. An imported blank placeholder is treated as unanswered; completing it creates a new current revision while preserving the original imported record. Reimport into such a changed live slot intentionally conflicts rather than replacing the candidate's submission.

## Candidate frontend

Start both services:

```sh
npm run dev
```

Open the private `personal_link` produced by `candidate:invite`. A bare http://localhost:3002/interview explains how to get a personal link; it does not select a candidate. The valid link shows the first unanswered question, a text/audio choice, submission receipts, and saved progress. It works without an account. Audio requires choosing a file; microphone recording and transcription are outside this flow.

The web uses same-origin server route handlers to proxy the API. Defaults require no additional configuration. For a different API host, copy `apps/web/.env.example` to `apps/web/.env.local` and set server-only `API_ORIGIN`. Next loads its environment from `apps/web`; the root Python `.env` is separate. Rebuild/restart web after changing the proxy destination. Never put model keys or database credentials in a frontend variable. If changing the 20 MiB backend upload cap, align the frontend file cap too; the proxy streams uploads and Python enforces the byte cap.

The token remains in the URL fragment so the same link works after a reload. It is not stored in cookies or browser storage. Keep the personal link private. Only accepted answers survive a reload; unsent draft text and selected files stay in memory and are lost if you reload or leave. Following a connection error, retry an unchanged answer or use Check saved progress. The API preserves accepted answers and receipts.

Frontend checks:

```sh
npm run test:web
npm run build
npm run check:web
```

Frontend tests use Node's test runner through tsx and do not call the live API. Live browser verification is separate and uses labelled synthetic demo data. The current client suite has 20 checks. The backend's previously verified suite remains 125 checks.

To run the production build locally:

```sh
npm run build
npm run start --workspace @talent-review/web -- --hostname 127.0.0.1
```

Keep the API running. Browser verification used this production mode because the agent sandbox denied Turbopack's macOS FSEvent watcher. If development watching has that environment-specific failure, use production mode to verify the app, or run the dev command from your normal terminal. Stop an existing web process before starting another on port 3002.

Verification covered one-question rendering, typed and audio acceptance, double-click protection, receipt acknowledgment, progress after reload, invalid-file feedback without advancement, completed interviews after reload, missing/invalid links, and a small-screen layout. Imported pack data was not edited; demo A's six answers are separate synthetic verification data. Both candidate and HR interfaces are implemented; live scoring remains pending.

## Backend HR verification and Swagger

Root `.env` contains `HR_DEMO_EMAIL`, `HR_DEMO_NAME`, `HR_DEMO_PASSWORD`, and `HR_SESSION_HOURS`. Local credentials implement explicitly mocked sign-in; no email is sent. `.env.example` leaves the password blank, disabling sign-in until configured. This checkout has a generated private password in `.env`. Restart `npm run dev:api` after changing settings. Keep the API bound to loopback for this local demonstration.

1. Open `http://localhost:8000/docs`; execute `POST /hr/session` with email/password from `.env`. The response identifies authentication as `demo` and returns an expiring token.
2. Click Authorize and paste only the token into **HRSession**, leaving CandidateLink separate. Swagger does not retain authorization across reloads.
3. `GET /hr/roles` → `GET /hr/roles/{role_id}/candidates` → `GET /hr/applications/{application_id}`. Each question includes rubric and all revisions. Only `is_current=true` counts. `effective_score` stays null until there is a model suggestion or HR review.
4. `POST /hr/answers/{answer_id}/overrides` accepts `{"score":3,"reason":"Specific evidence meets rubric level 3"}`. Every accepted request appends an audit event. Existing suggestions remain unchanged. Audio and empty answers can be manually reviewed; doing so does not fabricate a model suggestion or change job status.
5. `GET /hr/jobs?status=failed` lists failures; `POST /hr/jobs/{job_id}/retry` queues the same failed job. Repeating while queued returns `requeued:false`; scored/human-review jobs return 409. `/hr/status` reports all four counts and whether a key is configured, never its value. Configured does not mean model access is verified.
6. Read `audio_url` from review and execute that GET with HRSession authorization. Storage paths are never exposed. Browser HR audio clients must fetch with Authorization and use the returned blob; a plain audio element cannot supply this bearer header.
7. `POST /hr/candidates` creates a candidate/application for an existing interview using name, email, interview_id. Duplicate normalized email returns 409. `GET /hr/interviews` lists interview IDs. `GET /hr/candidates/{candidate_id}/applications` locates existing applications.
8. `POST /hr/applications/{application_id}/invitations` with `{"days":7}` returns the raw personal link once. GET on that collection returns metadata only. Each POST deliberately creates a fresh link; `DELETE /hr/invitations/{invitation_id}` revokes one. No email delivery is performed.
9. `DELETE /hr/session` logs out. Reusing its token returns 401. Expired, revoked, inactive and candidate-token sessions cannot access HR records.

`npm run test:db` includes HR tests in isolated PostgreSQL schemas. The full backend suite passes 143 tests. Live checks loaded five roles and all 20 applications (18 imported plus two labelled demos), read private audio with HR authorization, rejected anonymous audio, and verified logout. Override/retry writes were tested only in isolated schemas; no artificial model results or failures were inserted into the application database. OpenAPI and Swagger expose typed request/response schemas, validation bounds and separate authorization schemes. No new database migration is needed; Alembic remains at 0003.

## HR frontend walkthrough

Start the API and web service, then open `/hr` (currently verified at `http://localhost:3002/hr`). Sign in with `HR_DEMO_EMAIL` and `HR_DEMO_PASSWORD` from root `.env`; the screen labels authentication as demo. Use the role selector and choose a candidate. Every question includes its grading guide, current answer, previous revisions where present, original suggestion/reason when available, job state, and effective score. No suggestion appears until the live worker has actually stored one.

Choose score 1–4 and enter a reason to save an override. The success message and updated effective score confirm acceptance; Review history shows the audit entry. If the connection fails during a write, refresh and inspect history before submitting again. Earlier revisions are read-only in this interface. Model suggestion and job status remain separate from manual review.

For audio answers, select Load private audio, then use the audio controls. The browser fetches the file with HR authorization and creates a temporary blob URL; it does not expose a token or server path. Scoring jobs lists all four states and failure/review reasons, with pagination. Failed jobs expose Retry scoring job; the same action also appears beside failed answers. Refresh data reloads persisted states. A queued job does not imply the worker is running. Sign out revokes the session; reload/expiry requires signing in again.

Browser verification passed against the actual application API: sign-in, role candidates, six-answer review, a double-clicked override resulting in exactly one audit event, effective score/history after refresh, and WAV playback from an authenticated blob (valid metadata, no media error, playing state). The override is explicitly labelled synthetic verification on Swagger Demo Candidate A, not an evaluation of a real person. Original imported candidates/answers/jobs remain unchanged and model suggestions remain zero.

For failed-job UI verification, the same production frontend was served through a temporary local proxy to an API using a disposable PostgreSQL schema. Its failure was explicitly labelled a test fixture; no model was called. Double-clicking Retry scoring job changed the same job from failed to queued, preserved three lifetime attempts, and granted a six-attempt total budget. The temporary server and schema were removed after verification. No artificial failure was inserted into the application queue.

30 frontend client tests pass (20 candidate, 10 HR), with TypeScript and production build checks. HR tests cover authorization/proxy headers, login contracts, HTTP conflicts/401s, override payloads, audio blobs/content types, malformed responses, safe network errors and retry identity. Browser checks also cover invalid credentials and logout. Live OpenAI execution and a clean-machine walkthrough remain pending.

## Frontend refactor regression checks

Run `npm run check:web`, `npm run test:web`, and `npm run build`. The current results are 30 passing frontend client tests plus successful type checking/build; 143 backend tests also pass. Verify the actual viewport width and document scroll width when testing desktop/mobile. The latest audit checked 320/390/768/1280 pixels across public and HR screens, with no horizontal overflow on checked views.

Candidate regression: test missing/invalid links; submit text twice; confirm one receipt; reload to the next question; reject invalid audio without progress; submit a valid WAV; finish all six answers and reload the completed confirmation. HR regression: sign in, switch roles/candidates, refresh review, inspect current/history states, submit one score/reason, verify one audited override after a double-click, load private audio, retry a failed job, and sign out. Test write flows in a disposable PostgreSQL schema through the real API and production frontend. Do not seed artificial model results into the application database. The latest isolated browser verification data and uploads were cleaned up after use.

Audio upload has one visible labelled picker; the native input remains keyboard-accessible and focus highlights the upload area. Mobile input text uses 16px to avoid focus zoom. Unsubmitted draft/file state still lives only in memory. No live scoring verification is implied by these frontend checks.

## Repository-wide formatting and linting

Install tooling with root `npm install` and `uv sync --dev` inside `apps/api`. Dependency versions are recorded in the npm and uv lockfiles. Run all commands below from the repository root.

| Command                                                 | Purpose                                                                                               |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `npm run format`                                        | Prettier writes supported web/config/docs files; Ruff formats all Python source, migrations and tests |
| `npm run format:check`                                  | Read-only formatting verification for both toolchains                                                 |
| `npm run lint`                                          | ESLint Next.js/React/TypeScript checks and Ruff Python/import checks                                  |
| `npm run lint:fix`                                      | Apply automatic lint fixes; review changes, then run format                                           |
| `npm run check`                                         | Format check, lint and TypeScript; makes no source edits                                              |
| `npm run format:web` / `npm run format:api`             | Run one formatter                                                                                     |
| `npm run format:check:web` / `npm run format:check:api` | Check one formatter                                                                                   |
| `npm run lint:web` / `npm run lint:api`                 | Lint one language/toolchain                                                                           |
| `npm run lint:fix:web` / `npm run lint:fix:api`         | Apply fixes with one linter                                                                           |

Prettier covers supported files across the repository, not just web source. Ruff covers the entire Python application directory including migrations and tests. `.prettierignore`, ESLint global ignores and Ruff excludes omit dependencies, builds, caches, `.env` files, uploads and local runtime data. `.editorconfig` supplies editor indentation/newline defaults. Root `.env` secrets are never read or rewritten by these commands.

ESLint uses the matching Next.js core-web-vitals and TypeScript presets with the monorepo web root configured. Zero warnings are allowed. The advisory `react-hooks/set-state-in-effect` rule has a documented exception only for the two hooks that intentionally synchronize URL drafts and manual request loading state; Rules of Hooks and exhaustive dependency checks remain enabled. Ruff checks Python errors, unused imports/names and import ordering, targeting Python 3.11 syntax.

Recommended sequence before committing:

```bash
npm run lint:fix
npm run format
npm run check
npm run test:web
npm run test:db
npm run build
```

The check command does not replace tests, database verification or the production build. In a restricted agent environment, prefix uv-based commands with `UV_CACHE_DIR="$PWD/var/uv-cache"` to keep the cache inside the project.

## API outages and recovery

`/api/hr/...` and `/api/candidate/...` are handled by the Next.js server proxy. `API_ORIGIN` remains server-only and defaults to `http://127.0.0.1:8000`. Unreachable upstreams, invalid origin configuration and request timeouts return `503` with `{ "detail": "The API service is temporarily unavailable. Please try again shortly.", "code": "api_unavailable" }`, `Retry-After: 3`, and no-store privacy headers. No raw connection exception or submitted credentials are echoed. The proxy times out before the browser client and never automatically retries writes.

The frontend displays that detail and leaves an explicit retry available. Real API status codes and JSON bodies (401/409/415/422/etc.) remain intact. Only allowlisted request/response headers are forwarded; cookies are not. Multipart uploads retain their boundaries and stream through; private audio streams with range support. Python remains responsible for authorization, media/size limits and duplicate prevention.

Verification covered the production proxy with the real API stopped: HR sign-in and candidate interview returned readable 503 responses, and browser sign-in showed the retry message. Restarting restored sign-in. Healthy checks covered role/job reads, query filters, private audio/ranges, multipart rejection and logout. The combined development command was started, stopped and restarted successfully; both services use the documented ports. `WEB_ORIGIN` defaults/examples/local settings now match port 3002 so issued personal links use the running frontend.

## Theme verification

The header offers segmented Light, Dark and System buttons across public, candidate and HR pages. On small screens the buttons use compact icons with accessible labels. Role and score dropdowns use styled Radix menus; verify selection, selected checkmarks, keyboard navigation and Escape dismissal. System resolves to the browser/device preference and follows changes automatically. The browser remembers the choice under `talent-review.theme`; no account or invitation value is stored there.

Verify both explicit themes, reload persistence, navigation between public/HR/candidate pages, and System matching device appearance. Inspect cards, inputs/selects, progress, warning/status notices and native audio controls. Check the header at 320px and candidate forms at 390px for overflow. Use `npm run test:web` for the palette contrast regressions, and run `npm run check` plus the production build. The theme update passes 60 frontend tests, including 20 representative light/dark contrast checks. Browser verification confirms mode changes, persistence, system resolution and responsive candidate/HR screens. No answer or score was changed for these checks.

## Final verification without an OpenAI key

`npm run verify` requires a healthy PostgreSQL instance and runs format checks, ESLint/Ruff, TypeScript, frontend tests, ordinary backend tests, PostgreSQL integration tests and the production build. PostgreSQL fixtures use disposable schemas and remove them after testing. The new cross-service regression submits a candidate answer twice, observes a provider failure, retries through HR, processes one test-only suggestion, preserves it through an audited override, checks private audio, resume progress and logout. Fake model results remain in isolated test schemas; the running scorer is still OpenAI.

Clean local setup was checked using a source-only copy under a temporary directory, excluding `.env`, dependencies, builds, uploads and runtime data. Fresh `npm ci` and `uv sync --locked` succeeded. A separate empty PostgreSQL database migrated to `0003`, loaded all 35 supplied answers, and passed read-only import verification. The copy passed the complete verification command. This checks fresh local state on macOS; it is not evidence of testing every operating system or a separate physical machine.

For your final walkthrough: open a personal link, show receipt/resume and audio acceptance; sign into `/hr`, review roles, answer revisions, audio and job states; demonstrate permission rejection and an override with its audit reason. Provider success, injection behavior and persisted live suggestions remain the only checks waiting for the OpenAI key. Test-only provider failures and crash recovery are already covered automatically. Do not replace the working scorer with a fake to demonstrate live scoring.
