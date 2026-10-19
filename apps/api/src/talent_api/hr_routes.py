"""Authenticated review API. Demo credentials are local configuration, not production SSO."""

import hashlib
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import hr_schemas as S
from .config import Settings, settings
from .db import get_db
from .models import (
    Answer,
    Application,
    Candidate,
    HRSession,
    HRUser,
    Interview,
    Invitation,
    Override,
    Question,
    Role,
    ScoringJob,
    Suggestion,
)
from .worker import RetryConflict, retry_job_in_session

router = APIRouter(
    prefix="/hr",
    responses={
        401: {"description": "Missing, expired, revoked, or invalid HR session"},
        404: {"description": "Record not found"},
        503: {"description": "Database or private storage unavailable"},
    },
)
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="HRSession",
    description="Demo HR bearer token returned by POST /hr/session. Candidate invitation tokens do not authorize HR routes.",
)


def get_settings():
    return settings


DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authorize(
    db: Session, credentials: HTTPAuthorizationCredentials | None
) -> tuple[HRSession, HRUser]:
    if (
        credentials is not None
        and credentials.scheme.lower() == "bearer"
        and len(credentials.credentials) == 43
    ):
        result = db.execute(
            select(HRSession, HRUser)
            .join(HRUser, HRSession.user_id == HRUser.id)
            .where(
                HRSession.token_hash == digest(credentials.credentials),
                HRSession.revoked_at.is_(None),
                HRSession.expires_at > func.clock_timestamp(),
                HRUser.is_active.is_(True),
            )
        ).first()
        if result:
            return result
    raise HTTPException(
        401, "A valid HR session is required", headers={"WWW-Authenticate": "Bearer"}
    )


def require(db, model, identifier):
    row = db.get(model, identifier)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def view(schema, row):
    return schema.model_validate(row, from_attributes=True)


def summary(db, application):
    candidate = require(db, Candidate, application.candidate_id)
    total = db.scalar(
        select(func.count())
        .select_from(Question)
        .where(Question.interview_id == application.interview_id)
    )
    count = db.scalar(
        select(func.count())
        .select_from(Answer)
        .where(
            Answer.application_id == application.id,
            Answer.is_current.is_(True),
            Answer.input_kind != "missing",
        )
    )
    return S.ApplicationSummary(
        id=application.id,
        candidate=view(S.CandidateSummary, candidate),
        interview_id=application.interview_id,
        answered_count=count,
        total_questions=total,
        complete=total == 6 and count == total,
    )


def answer_view(db, answer):
    job = db.scalar(select(ScoringJob).where(ScoringJob.answer_id == answer.id))
    suggestion = db.scalar(select(Suggestion).where(Suggestion.answer_id == answer.id))
    overrides = list(
        db.scalars(
            select(Override)
            .where(Override.answer_id == answer.id)
            .order_by(Override.created_at, Override.id)
        )
    )
    latest = overrides[-1] if overrides else None
    return S.AnswerView(
        id=answer.id,
        source_id=answer.source_id,
        is_current=answer.is_current,
        input_kind=answer.input_kind,
        text=answer.text_content,
        audio_url=f"/hr/answers/{answer.id}/audio" if answer.input_kind == "audio" else None,
        audio_mime_type=answer.audio_mime_type,
        duration_seconds=answer.duration_seconds,
        submitted_at=answer.submitted_at,
        source_submitted_at=answer.source_submitted_at,
        job=view(S.Job, job) if job else None,
        suggestion=view(S.SuggestionView, suggestion) if suggestion else None,
        overrides=[view(S.OverrideView, item) for item in overrides],
        effective_score=latest.score if latest else suggestion.score if suggestion else None,
        effective_score_source="hr" if latest else "model" if suggestion else None,
    )


@router.post(
    "/session",
    response_model=S.SessionCreated,
    tags=["HR authentication"],
    summary="Sign in using configured demo HR credentials",
    description="Mock sign-in for local use. Configure HR_DEMO_EMAIL and HR_DEMO_PASSWORD in the server .env. Returns a bearer token once; only its SHA-256 hash is stored. This is not production identity verification.",
)
def login(body: S.Login, db: DB, config: Config):
    password = config.hr_demo_password.get_secret_value()
    if not password:
        raise HTTPException(503, "Demo HR sign-in is not configured")
    if not (
        secrets.compare_digest(body.email.lower().encode(), config.hr_demo_email.lower().encode())
        and secrets.compare_digest(body.password.get_secret_value().encode(), password.encode())
    ):
        raise HTTPException(401, "Invalid demo credentials")
    with db.begin():
        # Serialize first-login bootstrap without a unique-email race.
        db.execute(text("SELECT pg_advisory_xact_lock(582943192)"))
        user = db.scalar(select(HRUser).where(HRUser.email == config.hr_demo_email.lower()))
        if user is None:
            user = HRUser(email=config.hr_demo_email.lower(), name=config.hr_demo_name)
            db.add(user)
            db.flush()
        if not user.is_active:
            raise HTTPException(403, "HR account is inactive")
        token = secrets.token_urlsafe(32)
        session = HRSession(
            user_id=user.id,
            token_hash=digest(token),
            expires_at=db.scalar(select(func.clock_timestamp()))
            + timedelta(hours=config.hr_session_hours),
        )
        db.add(session)
        db.flush()
        return S.SessionCreated(token=token, expires_at=session.expires_at, user=view(S.User, user))


@router.get(
    "/session",
    response_model=S.User,
    tags=["HR authentication"],
    summary="Read the authenticated HR identity",
)
def current(db: DB, credentials: Credentials):
    with db.begin():
        return view(S.User, authorize(db, credentials)[1])


@router.delete(
    "/session", status_code=204, tags=["HR authentication"], summary="Revoke the current session"
)
def logout(db: DB, credentials: Credentials):
    with db.begin():
        session, _ = authorize(db, credentials)
        session.revoked_at = db.scalar(select(func.clock_timestamp()))
    return Response(status_code=204)


@router.get("/roles", response_model=list[S.Named], summary="List roles")
def roles(db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        return [view(S.Named, row) for row in db.scalars(select(Role).order_by(Role.name))]


@router.get(
    "/interviews",
    response_model=list[S.InterviewSummary],
    summary="List interviews, optionally filtered by role",
)
def interviews(db: DB, credentials: Credentials, role_id: UUID | None = None):
    with db.begin():
        authorize(db, credentials)
        query = select(Interview).order_by(Interview.title, Interview.id)
        if role_id:
            query = query.where(Interview.role_id == role_id)
        return [view(S.InterviewSummary, row) for row in db.scalars(query)]


@router.get(
    "/candidates",
    response_model=list[S.CandidateSummary],
    summary="List candidates with bounded pagination",
)
def candidates(db: DB, credentials: Credentials, limit: Limit = 50, offset: Offset = 0):
    with db.begin():
        authorize(db, credentials)
        return [
            view(S.CandidateSummary, row)
            for row in db.scalars(
                select(Candidate).order_by(Candidate.name, Candidate.id).limit(limit).offset(offset)
            )
        ]


@router.get(
    "/roles/{role_id}/candidates",
    response_model=list[S.ApplicationSummary],
    summary="Review candidate progress within a role",
)
def role_candidates(
    role_id: UUID, db: DB, credentials: Credentials, limit: Limit = 50, offset: Offset = 0
):
    with db.begin():
        authorize(db, credentials)
        require(db, Role, role_id)
        rows = db.scalars(
            select(Application)
            .join(Interview, Interview.id == Application.interview_id)
            .where(Interview.role_id == role_id)
            .order_by(Application.created_at, Application.id)
            .limit(limit)
            .offset(offset)
        )
        return [summary(db, row) for row in rows]


@router.get(
    "/candidates/{candidate_id}/applications",
    response_model=list[S.ApplicationSummary],
    summary="List one candidate's interview applications",
)
def applications(candidate_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        require(db, Candidate, candidate_id)
        return [
            summary(db, row)
            for row in db.scalars(
                select(Application)
                .where(Application.candidate_id == candidate_id)
                .order_by(Application.created_at, Application.id)
            )
        ]


@router.post(
    "/candidates",
    response_model=S.ApplicationSummary,
    status_code=201,
    summary="Create a candidate and an interview application",
    responses={409: {"description": "Email already exists; use the existing candidate"}},
)
def create_candidate(body: S.CandidateCreate, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        interview = require(db, Interview, body.interview_id)
        if not interview.is_active:
            raise HTTPException(409, "Interview is inactive")
        # API-created identities serialize by normalized email; imported identities are retained.
        email = body.email.lower()
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 0))"), {"email": email}
        )
        if db.scalar(select(Candidate.id).where(func.lower(Candidate.email) == email)):
            raise HTTPException(409, "Candidate email already exists")
        candidate = Candidate(name=body.name, email=email)
        db.add(candidate)
        db.flush()
        application = Application(candidate_id=candidate.id, interview_id=interview.id)
        db.add(application)
        db.flush()
        return summary(db, application)


@router.get(
    "/applications/{application_id}",
    response_model=S.Review,
    summary="Review questions, all answer revisions, suggestions and audit history",
    description="Only is_current revisions count. Effective score uses the latest HR override, otherwise the original model suggestion. Missing/failed/unscored answers have no invented score.",
)
def review(application_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        application = require(db, Application, application_id)
        questions = db.scalars(
            select(Question)
            .where(Question.interview_id == application.interview_id)
            .order_by(Question.position)
        )
        return S.Review(
            application=summary(db, application),
            questions=[
                S.ReviewQuestion(
                    id=q.id,
                    number=q.position,
                    prompt=q.prompt,
                    rubric_version=q.rubric_version,
                    rubric={str(i): getattr(q, f"rubric_{i}") for i in range(1, 5)},
                    revisions=[
                        answer_view(db, a)
                        for a in db.scalars(
                            select(Answer)
                            .where(
                                Answer.application_id == application.id, Answer.question_id == q.id
                            )
                            .order_by(Answer.submitted_at, Answer.id)
                        )
                    ],
                )
                for q in questions
            ],
        )


@router.get(
    "/answers/{answer_id}",
    response_model=S.AnswerView,
    summary="Read an individual answer revision and review history",
)
def answer(answer_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        return answer_view(db, require(db, Answer, answer_id))


@router.post(
    "/answers/{answer_id}/overrides",
    response_model=S.OverrideView,
    status_code=201,
    summary="Append an audited HR score override",
    description="Requires an integer score 1–4 and a nonblank reason. Preserves the model suggestion and previous overrides. Does not change job status. Each accepted request appends an audit event.",
)
def override(answer_id: UUID, body: S.OverrideInput, db: DB, credentials: Credentials):
    with db.begin():
        _, user = authorize(db, credentials)
        # Serialize overrides so server timestamps establish a stable audit order.
        answer = db.scalar(select(Answer).where(Answer.id == answer_id).with_for_update())
        if answer is None:
            raise HTTPException(404, "Record not found")
        row = Override(
            answer_id=answer.id,
            actor_id=user.id,
            score=body.score,
            reason=body.reason,
            created_at=db.scalar(select(func.clock_timestamp())),
        )
        db.add(row)
        db.flush()
        return view(S.OverrideView, row)


@router.get(
    "/answers/{answer_id}/audio",
    response_class=FileResponse,
    summary="Stream private audio after HR authorization",
    responses={
        200: {
            "description": "Private audio bytes",
            "content": {"audio/mp4": {}, "audio/mpeg": {}, "audio/wav": {}},
        }
    },
)
def audio(answer_id: UUID, db: DB, credentials: Credentials, config: Config):
    with db.begin():
        authorize(db, credentials)
        row = require(db, Answer, answer_id)
        if row.input_kind != "audio" or not row.audio_path:
            raise HTTPException(404, "Audio not found")
        try:
            path = Path(row.audio_path).resolve(strict=True)
            root = config.hr_audio_root.resolve(strict=True)
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or path.stat().st_size != row.audio_size_bytes
            ):
                raise OSError()
        except (OSError, RuntimeError):
            raise HTTPException(404, "Audio not found") from None
        return FileResponse(
            path,
            media_type=row.audio_mime_type,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )


@router.get(
    "/jobs",
    response_model=list[S.Job],
    tags=["Scoring operations"],
    summary="List jobs and visible failures with pagination",
)
def jobs(
    db: DB,
    credentials: Credentials,
    status: Annotated[str | None, Query(pattern=r"^(queued|scored|failed|needs a person)$")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    with db.begin():
        authorize(db, credentials)
        query = select(ScoringJob).order_by(ScoringJob.created_at, ScoringJob.id)
        if status:
            query = query.where(ScoringJob.status == status)
        return [view(S.Job, row) for row in db.scalars(query.limit(limit).offset(offset))]


@router.get(
    "/jobs/{job_id}",
    response_model=S.Job,
    tags=["Scoring operations"],
    summary="Inspect one scoring job",
)
def job(job_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        return view(S.Job, require(db, ScoringJob, job_id))


@router.post(
    "/jobs/{job_id}/retry",
    response_model=S.RetryView,
    tags=["Scoring operations"],
    summary="Requeue a failed job without duplicating it",
    responses={409: {"description": "Job is scored or needs human review; retry is not allowed"}},
)
def retry(job_id: UUID, db: DB, credentials: Credentials, config: Config):
    with db.begin():
        authorize(db, credentials)
        require(db, ScoringJob, job_id)
        try:
            changed = retry_job_in_session(db, job_id, config)
        except RetryConflict as exc:
            raise HTTPException(409, str(exc)) from None
        db.flush()
        return S.RetryView(requeued=changed, job=view(S.Job, db.get(ScoringJob, job_id)))


@router.get(
    "/status",
    response_model=S.SystemStatus,
    tags=["Scoring operations"],
    summary="Read safe scoring configuration and all four job counts",
)
def status(db: DB, credentials: Credentials, config: Config):
    with db.begin():
        authorize(db, credentials)
        counts = {key: 0 for key in ("queued", "scored", "failed", "needs a person")}
        counts.update(
            dict(
                db.execute(
                    select(ScoringJob.status, func.count()).group_by(ScoringJob.status)
                ).all()
            )
        )
        return S.SystemStatus(
            live_scoring_configured=bool(config.openai_api_key.get_secret_value()),
            model=config.openai_model,
            job_counts=counts,
        )


@router.get(
    "/applications/{application_id}/invitations",
    response_model=list[S.InviteView],
    summary="List invitation metadata without exposing tokens",
)
def invitations(application_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        require(db, Application, application_id)
        return [
            view(S.InviteView, row)
            for row in db.scalars(
                select(Invitation)
                .where(Invitation.application_id == application_id)
                .order_by(Invitation.created_at, Invitation.id)
            )
        ]


@router.post(
    "/applications/{application_id}/invitations",
    response_model=S.InviteCreated,
    status_code=201,
    summary="Issue a personal link; the token is returned only once",
    description="Creates a new link per request. Existing links remain valid until expired or explicitly revoked. No email is sent.",
)
def invite(
    application_id: UUID, body: S.InviteInput, db: DB, credentials: Credentials, config: Config
):
    with db.begin():
        authorize(db, credentials)
        application = db.scalar(
            select(Application).where(Application.id == application_id).with_for_update()
        )
        if application is None:
            raise HTTPException(404, "Record not found")
        if not require(db, Interview, application.interview_id).is_active:
            raise HTTPException(409, "Interview is inactive")
        token = secrets.token_urlsafe(32)
        row = Invitation(
            application_id=application.id,
            token_hash=digest(token),
            expires_at=db.scalar(select(func.clock_timestamp())) + timedelta(days=body.days),
        )
        db.add(row)
        db.flush()
        return S.InviteCreated(
            **view(S.InviteView, row).model_dump(),
            token=token,
            personal_link=f"{config.web_origin.rstrip('/')}/interview#token={token}",
        )


@router.delete("/invitations/{invitation_id}", status_code=204, summary="Revoke a personal link")
def revoke(invitation_id: UUID, db: DB, credentials: Credentials):
    with db.begin():
        authorize(db, credentials)
        row = require(db, Invitation, invitation_id)
        # Same application lock as candidate submissions makes revocation deterministic.
        db.scalar(select(Application).where(Application.id == row.application_id).with_for_update())
        row.revoked_at = db.scalar(select(func.clock_timestamp()))
    return Response(status_code=204)


# Give each operation one Swagger group instead of duplicating HR operations.
for route in router.routes:
    if not route.tags:
        route.tags = ["HR review"]
