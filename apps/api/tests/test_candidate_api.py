"""Candidate permission, durability, input, and concurrency tests against PostgreSQL."""

import io
import json
import os
import secrets
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from talent_api.candidate_routes import get_settings
from talent_api.candidate_service import issue_invitation
from talent_api.config import Settings
from talent_api.db import get_db
from talent_api.main import app
from talent_api.models import (
    Answer,
    Application,
    Candidate,
    HRSession,
    HRUser,
    Interview,
    Invitation,
    Question,
    Role,
    ScoringJob,
    SubmissionKey,
    Suggestion,
)
from talent_api.storage import digest

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1")


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\x00\x00" * 800)
    return stream.getvalue()


def seed(factory):
    def add(session, cls, **values):
        obj = cls(**values)
        session.add(obj)
        session.flush()
        return obj

    records = []
    for name in ["Candidate A", "Candidate B"]:
        with factory() as session, session.begin():
            role = add(session, Role, name=name + str(uuid4()))
            interview = add(session, Interview, role_id=role.id, title="Candidate test interview")
            candidate = add(
                session, Candidate, name=name, email=name.replace(" ", ".") + "@example.test"
            )
            application = add(
                session, Application, candidate_id=candidate.id, interview_id=interview.id
            )
            questions = [
                add(
                    session,
                    Question,
                    interview_id=interview.id,
                    position=i,
                    source_id=f"Q{i}",
                    prompt=f"Describe example {i}",
                    rubric_version="test",
                    rubric_1="No evidence",
                    rubric_2="Vague",
                    rubric_3="Specific",
                    rubric_4="Measured",
                ).id
                for i in range(1, 7)
            ]
            aid = application.id
        with factory() as session:
            invite, token = issue_invitation(session, aid)
        records.append(
            dict(
                application_id=aid,
                questions=questions,
                token=token,
                invitation_id=invite.id,
                interview_id=interview.id,
            )
        )
    return records


@pytest.fixture
def api(db, tmp_path):
    factory = sessionmaker(
        bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    records = seed(factory)
    config = Settings(_env_file=None, candidate_audio_dir=tmp_path / "private-audio")

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_settings] = lambda: config
    try:
        with TestClient(app) as client:
            yield client, records, factory, config
    finally:
        app.dependency_overrides.clear()


def auth(record, key=None):
    result = {"Authorization": "Bearer " + record["token"]}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def endpoint(record, number=1, kind="answer"):
    return f"/candidate/questions/{record['questions'][number - 1]}/{kind}"


def counts(factory):
    with factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(cls))
            for cls in [Answer, ScoringJob, SubmissionKey]
        )


def test_personal_link_questions_and_safe_public_contract(api):
    client, records, factory, _ = api
    response = client.get("/candidate/interview", headers=auth(records[0]))
    assert response.status_code == 200
    body = response.json()
    assert len(body["questions"]) == 6 and body["progress"]["answered_count"] == 0
    assert body["progress"]["next_question_id"] == str(records[0]["questions"][0])
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    for question in body["questions"]:
        assert set(question) == {"id", "number", "prompt"}
    with factory() as session:
        invitation = session.get(Invitation, records[0]["invitation_id"])
        assert invitation.token_hash == digest(records[0]["token"].encode())
        assert records[0]["token"] not in invitation.token_hash
    q = client.get(f"/candidate/questions/{records[0]['questions'][0]}", headers=auth(records[0]))
    assert q.status_code == 200 and q.json()["number"] == 1


@pytest.mark.parametrize(
    "header", [None, "Bearer invalid", "Bearer " + secrets.token_urlsafe(32), "Basic abc"]
)
def test_missing_invalid_unknown_tokens_rejected(api, header):
    client, records, _, _ = api
    headers = {} if header is None else {"Authorization": header}
    assert client.get("/candidate/interview", headers=headers).status_code == 401
    assert client.get("/candidate/progress", headers=headers).status_code == 401
    assert (
        client.post(
            endpoint(records[0]),
            headers={**headers, "Idempotency-Key": "test"},
            json={"text": "Answer"},
        ).status_code
        == 401
    )


@pytest.mark.parametrize("state", ["expired", "revoked", "inactive"])
def test_expired_revoked_and_inactive_links(api, state):
    client, records, factory, _ = api
    record = records[0]
    with factory() as session, session.begin():
        invitation = session.get(Invitation, record["invitation_id"])
        now = session.scalar(select(func.clock_timestamp()))
        if state == "expired":
            # Keep schema expiry > creation invariant valid while making the token expired.
            invitation.created_at = now - timedelta(days=2)
            invitation.expires_at = now - timedelta(days=1)
        elif state == "revoked":
            invitation.revoked_at = now
        else:
            session.get(Interview, record["interview_id"]).is_active = False
    expected = 403 if state == "inactive" else 401
    assert client.get("/candidate/interview", headers=auth(record)).status_code == expected
    assert (
        client.post(
            endpoint(record), headers=auth(record, "test"), json={"text": "Answer"}
        ).status_code
        == expected
    )


def test_scope_isolation_and_no_public_audio_or_hr_routes(api):
    client, records, factory, _ = api
    assert (
        client.get(
            f"/candidate/questions/{records[1]['questions'][0]}", headers=auth(records[0])
        ).status_code
        == 404
    )
    assert (
        client.post(
            endpoint(records[1]), headers=auth(records[0], "test"), json={"text": "Answer"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            endpoint(records[1], kind="audio"),
            headers=auth(records[0], "test"),
            files={"file": ("test.wav", wav_bytes(), "audio/wav")},
        ).status_code
        == 404
    )
    assert client.get("/candidate/candidates/anything", headers=auth(records[0])).status_code == 404
    assert (
        client.get("/hr/roles", headers=auth(records[0])).status_code == 401
    )  # Candidate links cannot authorize HR.
    assert client.get("/uploads/test.wav", headers=auth(records[0])).status_code == 404
    assert counts(factory) == (0, 0, 0)


def test_text_receipt_duplicates_and_persisted_resume(api):
    client, records, factory, _ = api
    record = records[0]
    response = client.post(
        endpoint(record), headers=auth(record, "first"), json={"text": "My contribution"}
    )
    assert response.status_code == 201 and response.json()["accepted"]
    original = response.json()
    assert set(original) == {"accepted", "receipt", "question_id", "input_kind", "submitted_at"}
    for key in ["first", "different-key"]:
        repeat = client.post(
            endpoint(record), headers=auth(record, key), json={"text": "My contribution"}
        )
        assert repeat.status_code == 200 and repeat.json() == original
    assert counts(factory) == (1, 1, 2)
    with TestClient(app) as reopened:
        progress = reopened.get("/candidate/progress", headers=auth(record)).json()
    assert progress["answered_count"] == 1
    assert progress["next_question_id"] == str(record["questions"][1])
    assert progress["questions"][0]["receipt"] == original


def test_changed_payload_same_key_and_out_of_order_submissions_conflict(api):
    client, records, factory, _ = api
    record = records[0]
    assert (
        client.post(
            endpoint(record, 2), headers=auth(record, "later"), json={"text": "Too early"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            endpoint(record), headers=auth(record, "first"), json={"text": "Accepted"}
        ).status_code
        == 201
    )
    for key in ["first", "new-key"]:
        assert (
            client.post(
                endpoint(record), headers=auth(record, key), json={"text": "Changed"}
            ).status_code
            == 409
        )
    assert (
        client.post(
            endpoint(record, 2), headers=auth(record, "first"), json={"text": "Accepted"}
        ).status_code
        == 409
    )
    assert counts(factory) == (1, 1, 1)


@pytest.mark.parametrize(
    "body",
    [
        {"text": " "},
        {"text": ""},
        {"text": 4},
        {"text": "x" * 50001},
        {"text": "Answer", "candidate_id": str(uuid4())},
        {"text": "Answer", "score": 4},
    ],
)
def test_invalid_text_and_injected_identity_fields_are_rejected(api, body):
    client, records, factory, _ = api
    assert (
        client.post(endpoint(records[0]), headers=auth(records[0], "test"), json=body).status_code
        == 422
    )
    assert counts(factory) == (0, 0, 0)


@pytest.mark.parametrize("key", [None, " ", "x" * 201])
def test_idempotency_key_is_required_and_validated(api, key):
    client, records, _, _ = api
    assert (
        client.post(
            endpoint(records[0]), headers=auth(records[0], key), json={"text": "Answer"}
        ).status_code
        == 422
    )


def test_audio_private_storage_receipt_and_duplicate_file(api):
    client, records, factory, config = api
    record = records[0]
    data = wav_bytes()
    first = client.post(
        endpoint(record, kind="audio"),
        headers=auth(record, "audio"),
        files={"file": ("../../escape.wav", data, "audio/wav")},
    )
    assert first.status_code == 201 and first.json()["input_kind"] == "audio"
    again = client.post(
        endpoint(record, kind="audio"),
        headers=auth(record, "audio-again"),
        files={"file": ("different.wav", data, "audio/wav")},
    )
    assert again.status_code == 200 and again.json() == first.json()
    assert counts(factory) == (1, 1, 2)
    files = list(config.candidate_audio_dir.glob("*.wav"))
    assert len(files) == 1 and files[0].read_bytes() == data
    assert files[0].stat().st_mode & 0o077 == 0
    with factory() as session:
        job = session.scalar(select(ScoringJob))
        assert job.status == "needs a person" and job.review_reason
        assert session.scalar(select(func.count()).select_from(Suggestion)) == 0
    assert "audio_path" not in json.dumps(first.json())


@pytest.mark.parametrize(
    "data,mime,code",
    [
        (b"", "audio/wav", 422),
        (b"Not audio", "audio/wav", 415),
        (wav_bytes(), "audio/mpeg", 415),
        (b'{"token":"not audio"}', "application/json", 415),
    ],
)
def test_invalid_audio_not_stored(api, data, mime, code):
    client, records, factory, config = api
    response = client.post(
        endpoint(records[0], kind="audio"),
        headers=auth(records[0], "test"),
        files={"file": ("test.wav", data, mime)},
    )
    assert response.status_code == code
    assert counts(factory) == (0, 0, 0)
    assert not config.candidate_audio_dir.exists()


def test_audio_size_limit_is_enforced(api):
    client, records, factory, config = api
    limited = config.model_copy(update={"candidate_max_audio_bytes": 1024})
    app.dependency_overrides[get_settings] = lambda: limited
    response = client.post(
        endpoint(records[0], kind="audio"),
        headers=auth(records[0], "large"),
        files={"file": ("test.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 413 and counts(factory) == (0, 0, 0)


def test_all_questions_complete_and_scoring_data_never_leaks(api):
    client, records, factory, _ = api
    record = records[0]
    for i in range(1, 7):
        assert (
            client.post(
                endpoint(record, i), headers=auth(record, str(i)), json={"text": f"Answer {i}"}
            ).status_code
            == 201
        )
    with factory() as session, session.begin():
        job = session.scalar(select(ScoringJob).limit(1))
        job.status = "scored"
        session.add(
            Suggestion(
                answer_id=job.answer_id,
                job_id=job.id,
                score=4,
                reason="Private HR evidence",
                model="test-only",
                response_id="resp-test",
                rubric_version="test",
                prompt_version="test",
            )
        )
    response = client.get("/candidate/interview", headers=auth(record))
    progress = response.json()["progress"]
    assert (
        progress["complete"]
        and progress["answered_count"] == 6
        and progress["next_question_id"] is None
    )
    serialized = response.text
    for forbidden in [
        "rubric",
        "Private HR evidence",
        '"score"',
        '"status"',
        "response_id",
        "candidate_id",
        "audio_path",
        "token_hash",
    ]:
        assert forbidden not in serialized


def test_imported_blank_is_unanswered_and_can_be_replaced(api):
    client, records, factory, _ = api
    record = records[0]
    with factory() as session, session.begin():
        old = Answer(
            application_id=record["application_id"],
            interview_id=record["interview_id"],
            question_id=record["questions"][0],
            input_kind="missing",
            text_content="",
            source_id="A007",
            content_hash="a" * 64,
        )
        session.add(old)
        session.flush()
        session.add(
            ScoringJob(answer_id=old.id, status="needs a person", review_reason="Missing content")
        )
        old_id = old.id
    assert client.get("/candidate/progress", headers=auth(record)).json()["answered_count"] == 0
    assert (
        client.post(
            endpoint(record), headers=auth(record, "replacement"), json={"text": "Real answer"}
        ).status_code
        == 201
    )
    with factory() as session:
        assert session.get(Answer, old_id).is_current is False
    assert counts(factory) == (2, 2, 1)


def test_atomic_submission_rolls_back_answer_and_key_if_job_write_fails(api):
    client, records, factory, _ = api

    def fail(mapper, connection, target):
        raise IntegrityError("Simulated write failure", {}, Exception())

    event.listen(ScoringJob, "before_insert", fail)
    try:
        response = client.post(
            endpoint(records[0]), headers=auth(records[0], "retry-me"), json={"text": "Answer"}
        )
    finally:
        event.remove(ScoringJob, "before_insert", fail)
    assert response.status_code == 409 and counts(factory) == (0, 0, 0)
    assert (
        client.post(
            endpoint(records[0]), headers=auth(records[0], "retry-me"), json={"text": "Answer"}
        ).status_code
        == 201
    )


def test_swagger_contract_documents_auth_json_and_multipart(api):
    client, _, _, _ = api
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "CandidateLink" in schema["components"]["securitySchemes"]
    for path in [
        "/candidate/interview",
        "/candidate/progress",
        "/candidate/questions/{question_id}",
    ]:
        assert schema["paths"][path]["get"]["security"] == [{"CandidateLink": []}]
    assert (
        "multipart/form-data"
        in schema["paths"]["/candidate/questions/{question_id}/audio"]["post"]["requestBody"][
            "content"
        ]
    )
    assert (
        "application/json"
        in schema["paths"]["/candidate/questions/{question_id}/answer"]["post"]["requestBody"][
            "content"
        ]
    )


@pytest.mark.parametrize(
    "same_key,same_content", [(True, True), (False, True), (True, False), (False, False)]
)
def test_concurrent_double_clicks_and_conflicts_are_atomic(
    committed_factory, tmp_path, same_key, same_content
):
    factory = committed_factory
    record = seed(factory)[0]

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, candidate_audio_dir=tmp_path / "private"
    )

    def send(i):
        with TestClient(app) as client:
            key = "same" if same_key else f"request-{i}"
            value = "Same answer" if same_content else f"Answer {i}"
            return client.post(endpoint(record), headers=auth(record, key), json={"text": value})

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, range(2)))
        assert sorted(r.status_code for r in responses) == (
            [200, 201] if same_content else [201, 409]
        )
        assert counts(factory) == (1, 1, 2 if same_content and not same_key else 1)
        if same_content:
            assert responses[0].json()["receipt"] == responses[1].json()["receipt"]
    finally:
        app.dependency_overrides.clear()


def test_hr_session_token_does_not_authorize_candidate_endpoints(api):
    client, _, factory, _ = api
    token = secrets.token_urlsafe(32)
    with factory() as session, session.begin():
        user = HRUser(name="Test HR", email="hr@example.test")
        session.add(user)
        session.flush()
        session.add(
            HRSession(
                user_id=user.id,
                token_hash=digest(token.encode()),
                expires_at=session.scalar(select(func.clock_timestamp())) + timedelta(days=1),
            )
        )
    assert (
        client.get("/candidate/interview", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_streamed_request_is_limited_before_multipart_parsing(api, monkeypatch):
    from talent_api import request_limits

    client, records, factory, config = api
    monkeypatch.setattr(
        request_limits, "settings", config.model_copy(update={"candidate_max_audio_bytes": 1024})
    )
    response = client.post(
        endpoint(records[0], kind="audio"),
        headers={**auth(records[0], "chunked"), "Content-Type": "application/octet-stream"},
        content=(b"x" * 40000 for _ in range(2)),
    )
    assert response.status_code == 413 and counts(factory) == (0, 0, 0)


def test_oversized_json_is_limited_before_validation(api):
    client, records, factory, _ = api
    response = client.post(
        endpoint(records[0]), headers=auth(records[0], "large-json"), json={"text": "x" * 300000}
    )
    assert response.status_code == 413 and counts(factory) == (0, 0, 0)


def test_database_outage_returns_safe_retryable_http_error(api, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from talent_api import candidate_routes

    client, records, _, _ = api

    def unavailable(*args):
        raise OperationalError("private connection details", {}, Exception())

    monkeypatch.setattr(candidate_routes, "get_interview", unavailable)
    response = client.get("/candidate/interview", headers=auth(records[0]))
    assert response.status_code == 503 and "private connection" not in response.text


def test_storage_failure_returns_safe_error_and_no_partial_submission(api, monkeypatch):
    from talent_api import candidate_service

    client, records, factory, _ = api

    def unavailable(*args):
        raise OSError("private disk path")

    monkeypatch.setattr(candidate_service, "store_audio", unavailable)
    response = client.post(
        endpoint(records[0], kind="audio"),
        headers=auth(records[0], "storage-failure"),
        files={"file": ("test.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 503 and "private disk" not in response.text
    assert counts(factory) == (0, 0, 0)
