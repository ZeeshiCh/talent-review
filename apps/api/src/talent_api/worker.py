"""Durable PostgreSQL scoring worker and local maintenance CLI.

Provider calls happen outside transactions. A lease token fences stale workers; the
suggestion and final status commit together. No candidate/HR HTTP routes are exposed here.
"""

import argparse
import json
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Settings, settings
from .db import SessionLocal
from .models import Answer, Question, ScoringJob
from .models import Suggestion as StoredSuggestion
from .scoring import OpenAIScorer, ScoreOutput, ScoringError, ScoringInput, Suggestion

SessionFactory = Callable[[], Session]


class Scorer(Protocol):
    def score(self, answer: ScoringInput) -> Suggestion: ...


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    answer_id: UUID
    lease_token: UUID
    input: ScoringInput | None
    review_reason: str | None = None
    invalid_input: bool = False


@dataclass(frozen=True)
class Outcome:
    job_id: UUID
    status: str


class RetryConflict(ValueError):
    pass


def clear_lease(job: ScoringJob) -> None:
    job.lease_token = None
    job.lease_expires_at = None


def clear_errors(job: ScoringJob) -> None:
    job.error_code = None
    job.error_message = None
    job.review_reason = None
    job.retryable = False
    job.retry_at = None


def set_failure(session: Session, job: ScoringJob, error: ScoringError, config: Settings) -> None:
    now = session.scalar(select(func.clock_timestamp()))
    clear_lease(job)
    clear_errors(job)
    job.status = "failed"
    job.error_code = error.code
    job.error_message = str(error)
    job.retryable = error.retryable and job.attempts < job.max_attempts
    if job.retryable:
        delay = min(
            config.worker_retry_max_seconds,
            config.worker_retry_base_seconds * 2 ** min(max(job.attempts - 1, 0), 16),
        )
        job.retry_at = now + timedelta(seconds=delay)
    job.updated_at = now


def claim_job(
    factory: SessionFactory = SessionLocal,
    config: Settings = settings,
    *,
    job_id: UUID | None = None,
) -> Claim | None:
    with factory() as session, session.begin():
        while True:
            now = session.scalar(select(func.clock_timestamp()))
            ready = or_(
                and_(
                    ScoringJob.status == "queued",
                    ScoringJob.available_at <= now,
                    or_(ScoringJob.lease_token.is_(None), ScoringJob.lease_expires_at <= now),
                ),
                and_(
                    ScoringJob.status == "failed",
                    ScoringJob.retryable.is_(True),
                    ScoringJob.retry_at <= now,
                ),
            )
            statement = select(ScoringJob).where(ready)
            if job_id is not None:
                statement = statement.where(ScoringJob.id == job_id)
            job = session.scalar(
                statement.order_by(ScoringJob.available_at, ScoringJob.created_at, ScoringJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.attempts >= job.max_attempts:
                set_failure(
                    session,
                    job,
                    ScoringError(
                        "attempts_exhausted",
                        "Scoring attempt limit reached; explicit retry required",
                    ),
                    config,
                )
                session.flush()
                continue
            # A committed suggestion is authoritative if legacy/manual data left the job queued.
            if (
                session.scalar(
                    select(StoredSuggestion.id).where(StoredSuggestion.answer_id == job.answer_id)
                )
                is not None
            ):
                clear_lease(job)
                clear_errors(job)
                job.status = "scored"
                job.updated_at = now
                session.flush()
                continue
            clear_errors(job)
            job.status = "queued"  # Public vocabulary has no separate processing state.
            job.attempts += 1
            job.lease_token = uuid4()
            job.lease_expires_at = now + timedelta(seconds=config.worker_lease_seconds)
            job.updated_at = now
            answer = session.get(Answer, job.answer_id)
            if answer.input_kind != "text":
                reason = (
                    "Audio transcription is not implemented; HR review required."
                    if answer.input_kind == "audio"
                    else "Answer has no content; HR review required."
                )
                return Claim(job.id, job.answer_id, job.lease_token, None, review_reason=reason)
            question = session.get(Question, answer.question_id)
            try:
                scoring_input = ScoringInput(
                    question=question.prompt,
                    rubric={str(i): getattr(question, f"rubric_{i}") for i in range(1, 5)},
                    rubric_version=question.rubric_version,
                    answer_text=answer.text_content,
                )
            except ValidationError:
                return Claim(job.id, job.answer_id, job.lease_token, None, invalid_input=True)
            return Claim(job.id, job.answer_id, job.lease_token, scoring_input)


def owned_job(session: Session, claim: Claim) -> ScoringJob | None:
    job = session.scalar(
        select(ScoringJob)
        .where(
            ScoringJob.id == claim.job_id,
            ScoringJob.answer_id == claim.answer_id,
            ScoringJob.status == "queued",
            ScoringJob.lease_token == claim.lease_token,
        )
        .with_for_update()
    )
    if job is None or job.lease_expires_at <= session.scalar(select(func.clock_timestamp())):
        return None
    return job


def finish_failure(
    claim: Claim,
    error: ScoringError,
    factory: SessionFactory = SessionLocal,
    config: Settings = settings,
) -> Outcome:
    with factory() as session, session.begin():
        job = owned_job(session, claim)
        if job is None:
            return Outcome(claim.job_id, "lease_lost")
        set_failure(session, job, error, config)
    return Outcome(claim.job_id, "failed")


def finish_review(claim: Claim, reason: str, factory: SessionFactory = SessionLocal) -> Outcome:
    with factory() as session, session.begin():
        job = owned_job(session, claim)
        if job is None:
            return Outcome(claim.job_id, "lease_lost")
        clear_lease(job)
        clear_errors(job)
        job.status, job.review_reason = "needs a person", reason
        job.updated_at = session.scalar(select(func.clock_timestamp()))
    return Outcome(claim.job_id, "needs a person")


def finish_success(
    claim: Claim, result: Suggestion, factory: SessionFactory = SessionLocal
) -> Outcome:
    with factory() as session, session.begin():
        job = owned_job(session, claim)
        if job is None:
            return Outcome(claim.job_id, "lease_lost")
        # The job lock serializes all writers; unique answer/job keys are the final guard.
        existing = session.scalar(
            select(StoredSuggestion.id).where(StoredSuggestion.answer_id == claim.answer_id)
        )
        if existing is None:
            session.add(
                StoredSuggestion(
                    answer_id=claim.answer_id,
                    job_id=claim.job_id,
                    score=result.output.score,
                    reason=result.output.reason,
                    model=result.model,
                    response_id=result.response_id,
                    rubric_version=result.rubric_version,
                    prompt_version=result.prompt_version,
                )
            )
        clear_lease(job)
        clear_errors(job)
        job.status = "scored"
        job.updated_at = session.scalar(select(func.clock_timestamp()))
    return Outcome(claim.job_id, "scored")


def process_one(
    scorer: Scorer,
    factory: SessionFactory = SessionLocal,
    config: Settings = settings,
    *,
    job_id: UUID | None = None,
) -> Outcome | None:
    claim = claim_job(factory, config, job_id=job_id)
    if claim is None:
        return None
    if claim.review_reason:
        return finish_review(claim, claim.review_reason, factory)
    if claim.invalid_input:
        return finish_failure(
            claim,
            ScoringError("invalid_input", "Stored answer or rubric failed scoring validation"),
            factory,
            config,
        )
    try:
        result = scorer.score(claim.input)
        # Validate again at the persistence boundary, even for alternate/test adapters.
        output = ScoreOutput.model_validate(result.output.model_dump())
        if result.rubric_version != claim.input.rubric_version or any(
            not isinstance(v, str) or not v.strip() or len(v) > limit
            for v, limit in [
                (result.model, 200),
                (result.response_id, 200),
                (result.prompt_version, 100),
            ]
        ):
            raise ScoringError("invalid_output", "Model result metadata failed validation")
        result = Suggestion(
            output, result.response_id, result.model, result.rubric_version, result.prompt_version
        )
    except ScoringError as error:
        return finish_failure(claim, error, factory, config)
    except (ValidationError, ValueError, TypeError, AttributeError):
        return finish_failure(
            claim,
            ScoringError("invalid_output", "Model result failed scoring validation"),
            factory,
            config,
        )
    except Exception:
        # No provider details, transcript, token, or credential enters a persisted error.
        return finish_failure(
            claim,
            ScoringError("unexpected_error", "Unexpected scorer failure; explicit retry required"),
            factory,
            config,
        )
    if output.needs_person:
        return finish_review(claim, output.review_reason, factory)
    return finish_success(claim, result, factory)


def retry_job(
    job_id: UUID, factory: SessionFactory = SessionLocal, config: Settings = settings
) -> bool:
    """Local maintenance service; future HR routes must authorize before calling it.

    Only failed jobs change. Repeated/concurrent retries of an already queued job
    return False without extending its budget or creating another job.
    """
    with factory() as session, session.begin():
        return retry_job_in_session(session, job_id, config)


def retry_job_in_session(session: Session, job_id: UUID, config: Settings = settings) -> bool:
    """Caller owns authorization and transaction; row lock serializes retries."""
    job = session.scalar(select(ScoringJob).where(ScoringJob.id == job_id).with_for_update())
    if job is None:
        raise RetryConflict("Scoring job does not exist")
    if job.status == "queued":
        return False
    if job.status != "failed":
        raise RetryConflict("Only failed jobs can be retried")
    if (
        session.scalar(
            select(StoredSuggestion.id).where(StoredSuggestion.answer_id == job.answer_id)
        )
        is not None
    ):
        raise RetryConflict("A stored suggestion already exists; it will not be overwritten")
    clear_lease(job)
    clear_errors(job)
    job.status = "queued"
    # attempts is a lifetime counter; explicit retry grants a fresh bounded budget.
    job.max_attempts = job.attempts + config.worker_retry_attempts
    job.available_at = session.scalar(select(func.clock_timestamp()))
    job.updated_at = job.available_at
    return True


def status_report(factory: SessionFactory = SessionLocal) -> dict:
    with factory() as session:
        counts = dict(
            session.execute(
                select(ScoringJob.status, func.count()).group_by(ScoringJob.status)
            ).all()
        )
        failed = session.execute(
            select(ScoringJob, Answer.source_id)
            .join(Answer, Answer.id == ScoringJob.answer_id)
            .where(ScoringJob.status == "failed")
            .order_by(ScoringJob.created_at)
        ).all()
        return {
            "job_statuses": counts,
            "suggestions": session.scalar(select(func.count()).select_from(StoredSuggestion)),
            "failed_jobs": [
                {
                    "job_id": str(j.id),
                    "answer_id": source_id,
                    "attempts": j.attempts,
                    "max_attempts": j.max_attempts,
                    "error_code": j.error_code,
                    "error_message": j.error_message,
                    "automatic_retry": j.retryable,
                    "retry_at": j.retry_at.isoformat() if j.retry_at else None,
                }
                for j, source_id in failed
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run the live OpenAI worker")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Attempt one ready job, then exit")
    mode.add_argument(
        "--drain",
        action="store_true",
        help="Process currently ready jobs, then exit; do not wait for future retries",
    )
    run.add_argument(
        "--max-jobs", type=int, default=None, help="Optional bound on claims processed"
    )
    run.add_argument("--job-id", type=UUID, default=None)
    commands.add_parser("status", help="Read job counts and safe failed-job details")
    retry = commands.add_parser("retry", help="Explicitly requeue a failed job")
    retry.add_argument("job_id", type=UUID)
    args = parser.parse_args()
    try:
        if args.command == "status":
            print(json.dumps(status_report(), indent=2), flush=True)
            return
        if args.command == "retry":
            print(
                json.dumps({"job_id": str(args.job_id), "requeued": retry_job(args.job_id)}),
                flush=True,
            )
            return
        if args.max_jobs is not None and args.max_jobs < 1:
            parser.error("--max-jobs must be positive")
        if (
            settings.worker_lease_seconds
            < settings.openai_timeout_seconds * (settings.openai_max_retries + 1) + 15
        ):
            parser.error(
                "WORKER_LEASE_SECONDS must exceed the configured provider retry/timeout budget by 15 seconds"
            )
        scorer = OpenAIScorer()  # Fail before claiming any job when credentials are absent.
        processed = 0
        try:
            while True:
                outcome = process_one(scorer, job_id=args.job_id)
                if outcome is not None:
                    processed += 1
                    print(
                        json.dumps({"job_id": str(outcome.job_id), "status": outcome.status}),
                        flush=True,
                    )
                if args.once or (args.max_jobs is not None and processed >= args.max_jobs):
                    break
                if outcome is None:
                    if args.drain or args.job_id is not None:
                        break
                    time.sleep(settings.worker_poll_seconds)
        finally:
            scorer.client.close()
        print(json.dumps({"processed": processed}), flush=True)
    except (ScoringError, RetryConflict) as error:
        parser.exit(1, f"Worker: {error}\n")
    except SQLAlchemyError:
        parser.exit(
            1,
            "Worker: database operation failed; any claimed job recovers after its lease expires.\n",
        )
    except KeyboardInterrupt:
        parser.exit(0, "Worker stopped; any in-flight claim recovers after lease expiry.\n")


if __name__ == "__main__":
    main()
