"""Opt-in PostgreSQL integration checks in an isolated, rolled-back schema.

RUN_DB_TESTS=1 enables these tests. No application rows are inserted or removed.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from talent_api.db import Base
from talent_api.models import (
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
    SubmissionKey,
    Suggestion,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 for PostgreSQL integration tests"
)


def add(db, entity_type, **kwargs):
    obj = entity_type(**kwargs)
    db.add(obj)
    db.flush()
    return obj


@pytest.fixture
def graph(db):
    role = add(db, Role, name="Schema test role")
    candidate = add(db, Candidate, name="Test candidate", email="schema@example.test")
    interview = add(db, Interview, role_id=role.id, title="Test interview")
    question = add(
        db,
        Question,
        interview_id=interview.id,
        source_id="Q1",
        position=1,
        prompt="Describe work",
        rubric_version="v1",
        rubric_1="No evidence",
        rubric_2="Vague",
        rubric_3="Specific",
        rubric_4="Measured",
    )
    application = add(db, Application, candidate_id=candidate.id, interview_id=interview.id)
    answer = add(
        db,
        Answer,
        application_id=application.id,
        interview_id=interview.id,
        question_id=question.id,
        input_kind="text",
        text_content="My contribution",
        content_hash="a" * 64,
        source_id="A-test",
    )
    invitation = add(
        db,
        Invitation,
        application_id=application.id,
        token_hash="b" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    user = add(db, HRUser, email="hr@example.test", name="Demo HR")
    return dict(
        role=role,
        candidate=candidate,
        interview=interview,
        question=question,
        application=application,
        answer=answer,
        invitation=invitation,
        user=user,
    )


def answer_values(g, **changes):
    return {
        "application_id": g["application"].id,
        "interview_id": g["interview"].id,
        "question_id": g["question"].id,
        "input_kind": "text",
        "text_content": "Different answer",
        "content_hash": "c" * 64,
        **changes,
    }


def reject(db, entity_type, **values):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            add(db, entity_type, **values)


def test_tables_and_revision_match_models(migrated_connection):
    conn, _, schema = migrated_connection
    assert set(inspect(conn).get_table_names(schema=schema)) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003"


def test_full_graph_and_audit_history(db, graph):
    g = graph
    job = add(db, ScoringJob, answer_id=g["answer"].id, status="scored")
    suggestion = add(
        db,
        Suggestion,
        answer_id=g["answer"].id,
        job_id=job.id,
        score=3,
        reason="Specific evidence",
        model="test-model",
        response_id="resp-test",
        rubric_version="v1",
        prompt_version="v1",
    )
    for score in [2, 4]:
        add(
            db,
            Override,
            answer_id=g["answer"].id,
            actor_id=g["user"].id,
            score=score,
            reason="HR reviewed evidence",
        )
    add(
        db,
        HRSession,
        user_id=g["user"].id,
        token_hash="e" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert db.scalar(select(Suggestion.score).where(Suggestion.id == suggestion.id)) == 3
    assert len(db.scalars(select(Override).where(Override.answer_id == g["answer"].id)).all()) == 2


def test_current_revision_and_duplicate_content_constraints(db, graph):
    reject(db, Answer, **answer_values(graph))
    graph["answer"].is_current = False
    db.flush()
    newer = add(db, Answer, **answer_values(graph))
    assert newer.is_current
    # Duplicate payload stays forbidden even when neither revision is current.
    reject(db, Answer, **answer_values(graph, is_current=False))
    reject(
        db,
        Answer,
        **answer_values(graph, is_current=False, content_hash="d" * 64, source_id="A-test"),
    )


def test_cross_interview_answer_is_rejected(db, graph):
    interview = add(db, Interview, role_id=graph["role"].id, title="Other interview")
    question = add(
        db,
        Question,
        interview_id=interview.id,
        source_id="Q1",
        position=1,
        prompt="Other question",
        rubric_version="v1",
        rubric_1="a",
        rubric_2="b",
        rubric_3="c",
        rubric_4="d",
    )
    reject(db, Answer, **answer_values(graph, question_id=question.id, is_current=False))


def test_idempotency_key_and_invitation_scope(db, graph):
    g = graph
    values = dict(
        invitation_id=g["invitation"].id,
        application_id=g["application"].id,
        answer_id=g["answer"].id,
        idempotency_key="request-1",
        payload_hash="a" * 64,
    )
    add(db, SubmissionKey, **values)
    reject(db, SubmissionKey, **values)
    other = add(db, Candidate, name="Other", email="other@example.test")
    application = add(db, Application, candidate_id=other.id, interview_id=g["interview"].id)
    invitation = add(
        db,
        Invitation,
        application_id=application.id,
        token_hash="f" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    reject(
        db,
        SubmissionKey,
        **{**values, "invitation_id": invitation.id, "idempotency_key": "request-2"},
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"input_kind": "text", "text_content": ""},
        {
            "input_kind": "audio",
            "text_content": None,
            "audio_path": "private/file.m4a",
            "audio_mime_type": "audio/mp4",
            "audio_size_bytes": 0,
        },
        {"input_kind": "missing", "text_content": "", "source_id": None},
        {"content_hash": "not-a-hash"},
        {"input_kind": "video"},
    ],
)
def test_invalid_answer_payload_rejected(db, graph, changes):
    reject(db, Answer, **answer_values(graph, is_current=False, **changes))


def test_audio_and_imported_empty_answer_are_supported(db, graph):
    add(
        db,
        Answer,
        **answer_values(
            graph,
            is_current=False,
            input_kind="audio",
            text_content=None,
            audio_path="private/test.m4a",
            audio_mime_type="audio/mp4",
            audio_size_bytes=100,
        ),
    )
    missing = add(
        db,
        Answer,
        **answer_values(
            graph,
            content_hash="d" * 64,
            is_current=False,
            input_kind="missing",
            text_content="",
            source_id="A-empty",
        ),
    )
    add(
        db,
        ScoringJob,
        answer_id=missing.id,
        status="needs a person",
        review_reason="Missing content",
    )


@pytest.mark.parametrize(
    "values",
    [
        {"status": "running"},
        {"status": "failed"},
        {"status": "needs a person"},
        {"attempts": -1},
        {"lease_token": uuid4()},
        {"status": "queued", "error_code": "stale", "error_message": "stale"},
    ],
)
def test_invalid_job_states_rejected(db, graph, values):
    reject(db, ScoringJob, answer_id=graph["answer"].id, **values)


def test_one_job_and_one_suggestion_per_revision(db, graph):
    g = graph
    job = add(db, ScoringJob, answer_id=g["answer"].id)
    reject(db, ScoringJob, answer_id=g["answer"].id)
    values = dict(
        answer_id=g["answer"].id,
        job_id=job.id,
        score=3,
        reason="Evidence",
        model="test",
        response_id="resp-test",
        rubric_version="v1",
        prompt_version="v1",
    )
    reject(db, Suggestion, **{**values, "score": 5})
    reject(db, Suggestion, **{**values, "reason": " "})
    add(db, Suggestion, **values)
    reject(db, Suggestion, **values)


def test_job_answer_mismatch_rejected(db, graph):
    other = add(db, Answer, **answer_values(graph, is_current=False))
    job = add(db, ScoringJob, answer_id=other.id)
    reject(
        db,
        Suggestion,
        answer_id=graph["answer"].id,
        job_id=job.id,
        score=2,
        reason="Evidence",
        model="test",
        response_id="resp-test",
        rubric_version="v1",
        prompt_version="v1",
    )


@pytest.mark.parametrize("changes", [{"reason": " "}, {"score": 0}, {"actor_id": uuid4()}])
def test_invalid_override_rejected(db, graph, changes):
    values = dict(
        answer_id=graph["answer"].id, actor_id=graph["user"].id, score=3, reason="HR evidence"
    )
    reject(db, Override, **{**values, **changes})


def test_hashes_expiry_and_question_limits(db, graph):
    reject(
        db,
        HRSession,
        user_id=graph["user"].id,
        token_hash="raw-token",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    reject(
        db,
        Invitation,
        application_id=graph["application"].id,
        token_hash="c" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    reject(
        db,
        Question,
        interview_id=graph["interview"].id,
        position=7,
        source_id="Q7",
        prompt="Invalid position",
        rubric_version="v1",
        rubric_1="a",
        rubric_2="b",
        rubric_3="c",
        rubric_4="d",
    )


def test_migration_roundtrip_preserves_existing_role(migrated_connection):
    conn, config, schema = migrated_connection
    # Savepoint protects the module fixture's schema and never touches public tables.
    with conn.begin_nested() as savepoint:
        identity = uuid4()
        conn.execute(
            text("INSERT INTO roles(id, name) VALUES (:id, :name)"),
            {"id": identity, "name": "Preserve me"},
        )
        command.downgrade(config, "0001")
        assert inspect(conn).get_table_names(schema=schema) == ["alembic_version", "roles"]
        command.upgrade(config, "head")
        assert (
            conn.execute(text("SELECT name FROM roles WHERE id=:id"), {"id": identity}).scalar_one()
            == "Preserve me"
        )
        savepoint.rollback()
