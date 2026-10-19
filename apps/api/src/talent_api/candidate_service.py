"""Candidate authorization and transaction-owned submission/progress operations."""

import json
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException
from mutagen import File as AudioFile
from mutagen import MutagenError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .candidate_schemas import InterviewPublic, Progress, QuestionProgress, QuestionPublic, Receipt
from .config import Settings, settings
from .models import (
    Answer,
    Application,
    Interview,
    Invitation,
    Question,
    Role,
    ScoringJob,
    SubmissionKey,
)
from .storage import StorageProblem, digest, store_audio


@dataclass(frozen=True)
class Access:
    invitation_id: UUID
    application_id: UUID
    interview_id: UUID


@dataclass(frozen=True)
class Payload:
    kind: str
    body: str
    content_hash: str
    audio: bytes | None = None
    mime: str | None = None
    suffix: str | None = None


def authorize(session: Session, token: str) -> Access:
    invitation = session.scalar(
        select(Invitation).where(Invitation.token_hash == digest(token.encode()))
    )
    now = session.scalar(select(func.clock_timestamp()))
    if invitation is None or invitation.revoked_at is not None or invitation.expires_at <= now:
        raise HTTPException(
            401, "Invalid or expired personal link", headers={"WWW-Authenticate": "Bearer"}
        )
    application = session.get(Application, invitation.application_id)
    interview = session.get(Interview, application.interview_id)
    if not interview.is_active:
        raise HTTPException(403, "Interview is unavailable")
    return Access(invitation.id, application.id, interview.id)


def scoped_question(session: Session, access: Access, question_id: UUID) -> Question:
    question = session.scalar(
        select(Question).where(
            Question.id == question_id, Question.interview_id == access.interview_id
        )
    )
    if question is None:
        raise HTTPException(404, "Question not found")
    return question


def receipt(answer: Answer) -> Receipt:
    return Receipt(
        receipt=answer.receipt,
        question_id=answer.question_id,
        input_kind=answer.input_kind,
        submitted_at=answer.submitted_at,
    )


def questions_and_progress(session: Session, access: Access) -> tuple[list[Question], Progress]:
    questions = session.scalars(
        select(Question)
        .where(Question.interview_id == access.interview_id)
        .order_by(Question.position)
    ).all()
    if len(questions) != 6 or [q.position for q in questions] != list(range(1, 7)):
        raise HTTPException(503, "Interview questions are not ready")
    answers = {
        a.question_id: a
        for a in session.scalars(
            select(Answer).where(
                Answer.application_id == access.application_id,
                Answer.is_current.is_(True),
                Answer.input_kind.in_(["text", "audio"]),
            )
        ).all()
    }
    progress = [
        QuestionProgress(
            question_id=q.id,
            answered=q.id in answers,
            receipt=receipt(answers[q.id]) if q.id in answers else None,
        )
        for q in questions
    ]
    next_id = next((p.question_id for p in progress if not p.answered), None)
    return list(questions), Progress(
        total_questions=6,
        answered_count=len(answers),
        complete=next_id is None,
        next_question_id=next_id,
        questions=progress,
    )


def get_interview(session: Session, token: str) -> InterviewPublic:
    with session.begin():
        access = authorize(session, token)
        interview = session.get(Interview, access.interview_id)
        role = session.get(Role, interview.role_id)
        questions, progress = questions_and_progress(session, access)
        return InterviewPublic(
            title=interview.title,
            role=role.name,
            questions=[
                QuestionPublic(id=q.id, number=q.position, prompt=q.prompt) for q in questions
            ],
            progress=progress,
        )


def text_payload(value: str) -> Payload:
    return Payload(
        "text",
        value,
        digest(
            json.dumps({"kind": "text", "body": value}, sort_keys=True, ensure_ascii=False).encode()
        ),
    )


def audio_payload(data: bytes, content_type: str | None, config: Settings = settings) -> Payload:
    if len(data) > config.candidate_max_audio_bytes:
        raise HTTPException(413, "Audio file exceeds the upload limit")
    if not data:
        raise HTTPException(422, "Audio file is empty")
    try:
        media = AudioFile(BytesIO(data))
        mapping = {
            MP4: ("audio/mp4", ".m4a", {"audio/mp4", "audio/m4a", "audio/x-m4a"}),
            MP3: ("audio/mpeg", ".mp3", {"audio/mpeg", "audio/mp3"}),
            WAVE: ("audio/wav", ".wav", {"audio/wav", "audio/x-wav", "audio/wave"}),
        }
        info = next((value for cls, value in mapping.items() if isinstance(media, cls)), None)
        if info is None or not math.isfinite(media.info.length) or media.info.length <= 0:
            raise ValueError("Unsupported or empty audio")
    except (MutagenError, ValueError, TypeError, AttributeError, EOFError):
        raise HTTPException(415, "Upload a valid M4A, MP3, or WAV audio file") from None
    mime, suffix, aliases = info
    declared = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if declared not in aliases | {"application/octet-stream"}:
        raise HTTPException(415, "Declared content type does not match the audio file")
    body = digest(data)
    return Payload(
        "audio",
        body,
        digest(
            json.dumps({"kind": "audio", "body": body}, sort_keys=True, ensure_ascii=False).encode()
        ),
        data,
        mime,
        suffix,
    )


def submit(
    session: Session,
    token: str,
    question_id: UUID,
    key: str,
    payload: Payload,
    config: Settings = settings,
) -> tuple[Receipt, bool]:
    """Commit answer, receipt, submission-key record, and job together; lock participation."""
    try:
        with session.begin():
            access = authorize(session, token)
            session.scalar(
                select(Application).where(Application.id == access.application_id).with_for_update()
            )
            # Recheck after waiting for concurrent submissions, including expiry/revocation.
            session.expire_all()
            access = authorize(session, token)
            scoped_question(session, access, question_id)
            payload_hash = digest(
                json.dumps(
                    {"question_id": str(question_id), "content_hash": payload.content_hash},
                    sort_keys=True,
                ).encode()
            )
            old_key = session.scalar(
                select(SubmissionKey).where(
                    SubmissionKey.invitation_id == access.invitation_id,
                    SubmissionKey.idempotency_key == key,
                )
            )
            if old_key is not None:
                if old_key.payload_hash != payload_hash:
                    raise HTTPException(
                        409, "Idempotency key was already used for a different submission"
                    )
                return receipt(session.get(Answer, old_key.answer_id)), False
            current = session.scalar(
                select(Answer).where(
                    Answer.application_id == access.application_id,
                    Answer.question_id == question_id,
                    Answer.is_current.is_(True),
                )
            )
            created = False
            if current is not None and current.input_kind != "missing":
                if current.content_hash != payload.content_hash:
                    raise HTTPException(409, "This question already has an accepted answer")
                answer = current
            else:
                _, progress = questions_and_progress(session, access)
                if progress.next_question_id != question_id:
                    raise HTTPException(409, "Answer the current question before continuing")
                if current is not None:
                    # An imported blank placeholder is not an accepted candidate answer.
                    current.is_current = False
                    session.flush()
                path = (
                    store_audio(config.candidate_audio_dir, payload.audio, payload.suffix)
                    if payload.audio is not None
                    else None
                )
                answer = Answer(
                    application_id=access.application_id,
                    interview_id=access.interview_id,
                    question_id=question_id,
                    input_kind=payload.kind,
                    text_content=payload.body if payload.kind == "text" else None,
                    content_hash=payload.content_hash,
                    audio_path=path,
                    audio_mime_type=payload.mime,
                    audio_size_bytes=len(payload.audio) if payload.audio is not None else None,
                )
                session.add(answer)
                session.flush()
                session.add(
                    ScoringJob(
                        answer_id=answer.id,
                        status="queued" if payload.kind == "text" else "needs a person",
                        review_reason=None
                        if payload.kind == "text"
                        else "Audio transcription is not implemented; HR review required.",
                    )
                )
                created = True
            session.add(
                SubmissionKey(
                    invitation_id=access.invitation_id,
                    application_id=access.application_id,
                    answer_id=answer.id,
                    idempotency_key=key,
                    payload_hash=payload_hash,
                )
            )
            session.flush()
            accepted = receipt(answer)
        return accepted, created
    except IntegrityError:
        # Cooperative API callers are serialized; constraints protect against other writers.
        raise HTTPException(
            409, "Submission conflicted; retry with the same idempotency key"
        ) from None
    except (StorageProblem, OSError):
        raise HTTPException(
            503, "Private storage is unavailable; retry with the same idempotency key"
        ) from None


def issue_invitation(
    session: Session, application_id: UUID, days: int = 7
) -> tuple[Invitation, str]:
    """Trusted local operation. No public token-creation endpoint exists."""
    if not 1 <= days <= 30:
        raise ValueError("Link lifetime must be between 1 and 30 days")
    with session.begin():
        application = session.scalar(
            select(Application).where(Application.id == application_id).with_for_update()
        )
        if application is None:
            raise ValueError("Application not found")
        if not session.get(Interview, application.interview_id).is_active:
            raise ValueError("Interview is unavailable")
        token = secrets.token_urlsafe(32)
        now = session.scalar(select(func.clock_timestamp()))
        invitation = Invitation(
            application_id=application.id,
            token_hash=digest(token.encode()),
            expires_at=now + timedelta(days=days),
        )
        session.add(invitation)
        session.flush()
    return invitation, token
