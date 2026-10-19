# Talent Review — project overview

Talent Review helps candidates submit interview answers and HR review rubric-based score suggestions. HR remains responsible for decisions. The application is a monorepo with a Next.js frontend, Python API, and PostgreSQL database.

## Product scope

- Personal candidate links without accounts; six questions shown one at a time.
- Typed answers and private audio uploads, durable receipts, and resume after reload.
- HR role/candidate views, suggested scores with reasons, job status, and score overrides with a required reason.
- Background text scoring through a real language model, validated before persistence.
- Duplicate-safe submissions and clear, retryable scoring failures.

Audio transcription, ranking, production sign-in, email delivery, deployment, and analytics are outside the initial scope. Audio will be stored and flagged for human review.

## Current state

Implemented: web/API scaffold, SQLAlchemy configuration, PostgreSQL Compose service, full domain schema and migrations, health checks, and a validated OpenAI scoring client with a manual smoke-check command. The repeatable data importer is implemented and the supplied pack is loaded. The background scoring worker and local job status/retry commands are implemented. Candidate API endpoints for personal-link access, questions, text/audio submissions, and resume progress are implemented and verified in Swagger. The Next.js candidate frontend is implemented at `/interview#token=...` and connected to the API. HR backend authentication, review, private audio, invitations, audited overrides, and job operations are implemented. The HR frontend at `/hr` supports sign-in, role candidates, answer review, audited overrides, private audio playback, and job retries. Live OpenAI access awaits a local API key and successful verification.

Verified: 60 frontend tests and 144 backend tests (with PostgreSQL enabled), formatting/lint checks, TypeScript, and the production build. Permission, concurrency, worker lease recovery and cross-service candidate/worker/HR checks pass. A clean local copy with fresh dependencies and an empty database has also been verified. PostgreSQL uses host port 5433; migration `0003` creates 13 domain tables plus Alembic metadata.

Imported: 5 roles, 18 candidates, six questions per role (30 question rows), and 35 answer revisions. Jobs are initialized as 29 queued and six needing human review. Separate labelled demo records were used for Swagger/frontend verification. Model suggestions have not been generated because live OpenAI verification is still pending.

## Documentation — six files

| File                                          | Purpose                                          |
| --------------------------------------------- | ------------------------------------------------ |
| [README.md](README.md)                        | Project overview and scope                       |
| [architecture.md](docs/architecture.md)       | Architecture, stack, data model, API boundaries  |
| [coding-patterns.md](docs/coding-patterns.md) | Code organization and implementation conventions |
| [rules.md](docs/rules.md)                     | Constraints and mandatory reliability rules      |
| [roadmap.md](docs/roadmap.md)                 | Roadmap and actual project progress              |
| [workflow.md](docs/workflow.md)               | Setup, run, test, build, and migration workflow  |

Start with the [development workflow](docs/workflow.md) to run the project. Keep these documents synchronized with verified behavior.

## Setup and verification

Requirements: Node.js 20.9+, npm, Python 3.11+, uv, and running Docker Desktop.

```sh
cp .env.example .env  # First setup only; keep an existing .env
npm ci
uv sync --project apps/api --locked
npm run db:up        # Waits for PostgreSQL health
npm run db:migrate
```

Set a private `HR_DEMO_PASSWORD` in `.env` before signing in. Leave `OPENAI_API_KEY` blank until you are ready for live scoring. Load your extracted data pack:

```sh
npm run data:import -- --pack-dir /absolute/path/to/business-systems-pack
npm run data:import -- --pack-dir /absolute/path/to/business-systems-pack --verify-only
npm run verify       # Format, lint, types, frontend/backend/DB tests and production build
npm run dev
```

`npm test` runs frontend and ordinary backend tests without requiring PostgreSQL; `npm run test:db` enables database integration checks in disposable schemas. `npm run verify` requires the database but no OpenAI key. See [workflow](docs/workflow.md) for personal links, individual commands and live scoring steps.

## Run frontend and API together

After the setup steps in the workflow, run from the repository root:

```bash
npm run dev
```

Open [Talent Review](http://localhost:3002/) or [HR sign-in](http://localhost:3002/hr). Swagger runs at http://localhost:8000/docs. The command starts both services with labelled logs; Ctrl+C stops both. Stop older standalone instances first to free ports 3002 and 8000. Database setup and the scoring worker remain separate steps.

If the API is unavailable, frontend API requests return HTTP 503 JSON and display a clear retry message. Authentication, validation, receipts and audio are still handled by FastAPI when it is available.

## HR API and Swagger

Open [Swagger](http://localhost:8000/docs) or [ReDoc](http://localhost:8000/redoc). HR sign-in is explicitly mocked for local development. Set `HR_DEMO_EMAIL` and a private `HR_DEMO_PASSWORD` in root `.env` (this checkout has a generated password there). No default password is shipped. Restart the API after environment changes.

1. Execute `POST /hr/session` with the configured email/password.
2. Copy the returned token into **Authorize → HRSession**.
3. List `/hr/roles`, choose `/hr/roles/{role_id}/candidates`, and open `/hr/applications/{application_id}` for questions, rubrics, revisions, job statuses, suggestions, and override history.
4. Submit score/reason to `/hr/answers/{answer_id}/overrides`; access private audio via its authenticated `audio_url`. Inspect `/hr/jobs` and retry failed jobs with `/hr/jobs/{job_id}/retry`.
5. `DELETE /hr/session` revokes the bearer token. CandidateLink is a separate authorization scheme.

All backend flows can be tested before adding the OpenAI key. Live scoring verification remains pending; start the worker after configuring the key. See the workflow for invitation creation and complete endpoint usage.

Open `/hr` on the frontend to sign in using the demo HR credentials in `.env`. Sessions are kept in memory; reloading requires signing in again. Candidate review and scoring jobs have explicit refresh controls. The currently verified production frontend is at `http://localhost:3002/hr`; the shared development command uses port 3002.

Frontend organization: route files compose reusable candidate/HR views from `apps/web/src/components`, with request/session state in `apps/web/src/hooks`. The latest desktop/mobile audit passed at 320/390/768/1280 pixels, including candidate receipts/resume, uploads, HR overrides/audio/retries, 60 frontend tests, type checking and production build.

## Formatting and linting

Run from the repository root after `npm install` and `cd apps/api && uv sync --dev`:

```bash
npm run format        # Format supported frontend/config/docs files and all Python files
npm run format:check  # Check formatting without changing files
npm run lint          # ESLint + Ruff; warnings fail the frontend lint check
npm run lint:fix      # Apply available safe lint fixes
npm run check         # Formatting checks + lint + TypeScript
```

Use `npm run lint:fix` followed by `npm run format` for cleanup. Tests and production build remain separate commands. Generated output, dependencies, local uploads/data, and environment files are excluded.

## Color themes

Use the theme buttons in the header on any page to choose **Light**, **Dark**, or **System**. System follows your device appearance. The preference is remembered across pages and reloads on this browser; only the theme choice is stored. Candidate and HR interfaces share the same palette, including forms, audio controls, notices and score cards.
