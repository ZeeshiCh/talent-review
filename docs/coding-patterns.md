# Coding patterns

These conventions guide new implementation. They do not imply that every proposed module already exists.

## Python backend

- Use snake_case modules/functions and PascalCase classes. Add type hints to application functions and keep request/response schemas explicit.
- Keep FastAPI route handlers thin: validate input and authorization, call a service, return a dedicated response schema. Services own business rules and transaction boundaries.
- Use SQLAlchemy 2 typed mappings (`Mapped`, `mapped_column`). Manage one session per request or worker unit of work; never share sessions between concurrent tasks.
- Keep synchronous database operations in synchronous route handlers or worker functions. Do not block an async handler with synchronous ORM/provider calls.
- Use `session.begin()` for atomic domain writes. Persist answer and job together; enforce uniqueness in PostgreSQL and handle integrity conflicts with rollback.
- Introduce separate candidate and HR response schemas. Never return ORM objects with implicit sensitive fields.
- Read settings from environment through the settings module. Inject database/model clients where substitution is useful for tests.
- Add schema changes through Alembic. Import all model modules into migration metadata; review generated SQL. Do not create tables automatically at server startup.
- Return safe API errors and log useful internal context without credentials, invitation tokens, or raw candidate answers.

## Next.js and TypeScript

- Use App Router routes under `src/app`; keep shared components and API helpers in focused modules when needed.
- Keep TypeScript strict. Use explicit domain/API types; avoid `any` and unchecked type assertions at response boundaries.
- Default to server components; add `"use client"` only for browser interaction/state.
- Keep loading, empty, success, and error states explicit. Treat API receipts as authoritative; derive resume progress from persisted answers.
- Keep business validation and permissions in Python. Frontend checks support usability only.
- Centralize API calls as the feature surface grows; handle non-2xx responses. Never put model keys or private database credentials in client code or `NEXT_PUBLIC_*` variables.
- Keep styling simple and readable. Prefer small components over speculative abstractions.

## Jobs and scoring

- Keep provider calls behind a model adapter. Only tests may use a fake adapter.
- Perform slow network calls outside long-held database transactions. Claim/finalize work in short transactions with lease ownership checks.
- Validate provider output before mapping it to stored fields. Store suggestions separately from audited HR overrides.
- Use public states exactly as documented in the architecture and rules. Do not invent frontend-only states that hide failures.

## Changes and review

Implement one vertical slice, inspect the diff, run relevant checks, and commit the verified change. Write tests around behavior, authorization, concurrency, and failure boundaries. Avoid tests that merely repeat implementation details. Update the roadmap with actual evidence and keep setup commands aligned with package scripts.

## HR review conventions

Authorize the HR bearer session inside each endpoint transaction before reading records or mutating state. Use explicit Pydantic response models; never include token hashes or private paths. Candidate and HR tokens are separate capabilities. Review returns immutable suggestion metadata and append-only override history with a computed effective score. Override timestamps come from the database after an answer lock; actor identity comes from the session. Every accepted override request appends an event; clients must prevent accidental repeated clicks. Job retry shares the worker service and retains lifetime attempts. Validation errors omit submitted values to avoid echoing credentials or candidate text.

HR frontend contracts live in `src/lib/hr-api.ts`; validate all JSON responses before rendering. Render candidate text and reasons as text, never HTML. Keep HR bearer credentials in component memory, guard writes with synchronous refs, and ignore stale read results after selection/session changes. Audio fetches must use Authorization; revoke generated object URLs when their component unmounts. Use server audit history as the source of truth after refresh. An uncertain override request must prompt review of saved history before another submission because each accepted override is an audit event.

## Frontend component boundaries

Keep route components focused on composition. Split screens into focused components rather than accumulating forms, audio handling, list rendering, and request orchestration in a single file. The HR route composes components from `src/components/hr`, with session/data orchestration in `src/hooks/use-hr-workspace.ts`. Each view accepts only the controller fields it consumes. `src/components/ui/select-field.tsx` wraps Radix Select with accessible keyboard navigation, form participation and consistent menu styling; use it for HR dropdowns. Shared icons and control styles live in `src/components/ui`. HR-specific styles live alongside the route in `src/app/hr/hr.css`.

Candidate screens follow the same composition pattern: `use-candidate-interview.ts` owns the personal token, draft, guarded submission, receipt and resume state; focused views live under `components/candidate`. Share brand/header/footer components under `components/ui`. Keep layout, answer form and terminal-state CSS separate. HR read loading belongs in `use-hr-review-data.ts`, while session/actions stay in `use-hr-workspace.ts`; track independent requests independently. Check narrow layouts using the actual rendered viewport and document scroll width, not an assumed device setting.

## Automated style checks

Use Prettier for TypeScript/JavaScript, CSS, JSON, YAML and Markdown; use Ruff for Python formatting/import order. Run `npm run format` and `npm run lint` from the root. `npm run check` combines non-mutating format/lint/type checks. Do not hand-maintain formatting that conflicts with the checked-in configuration. Review automatic lint fixes, and keep generated/private directories excluded. Use the shared `.editorconfig` defaults in editors. Lint does not validate runtime permissions or replace tests.

Use the server API proxy for upstream transport failures; do not add client-side availability probes before every mutation or retry writes automatically. Keep outage copy in `service-errors.ts` so HR and candidate clients handle non-JSON gateway failures consistently. Stream multipart data unchanged, pass only required headers, and leave domain authorization/validation to FastAPI. The combined `npm run dev` command is the normal local entry point.

## Theme styling

Use semantic CSS variables from `app/themes.css` instead of hard-coded colors in component/route styles. Keep text, surface, accent, warning and focus roles distinct so both palettes remain readable. Add all appearance controls through the shared header/theme components. The theme provider owns system preference and cross-tab persistence; do not store authentication data in the theme preference. Palette tests check representative text/background pairs at a minimum 4.5:1 contrast ratio; this is not a claim that every accessibility criterion has been audited.
