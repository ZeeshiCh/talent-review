"""HR authorization, review, audio, audit and retry contracts on isolated PostgreSQL."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from test_candidate_api import auth, endpoint, seed, wav_bytes

from talent_api.candidate_routes import get_settings as candidate_settings
from talent_api.config import Settings
from talent_api.db import get_db
from talent_api.hr_routes import digest, get_settings
from talent_api.main import app
from talent_api.models import Answer, HRSession, Override, ScoringJob, Suggestion

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1")


@pytest.fixture
def hr(db, tmp_path):
    factory = sessionmaker(
        bind=db.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    records = seed(factory)
    config = Settings(
        _env_file=None,
        hr_demo_password="local-test-password",
        candidate_audio_dir=tmp_path,
        hr_audio_root=tmp_path,
    )

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[candidate_settings] = lambda: config
    try:
        with TestClient(app) as client:
            response = client.post(
                "/hr/session",
                json={"email": config.hr_demo_email, "password": "local-test-password"},
            )
            assert response.status_code == 200, response.text
            session = response.json()
            yield (
                client,
                records,
                factory,
                config,
                {"Authorization": "Bearer " + session["token"]},
                session,
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    ["/hr/roles", "/hr/interviews", "/hr/candidates", "/hr/jobs", "/hr/status", "/hr/session"],
)
def test_hr_requires_hr_token(hr, path):
    client, records, _, _, headers, _ = hr
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth(records[0])).status_code == 401
    assert client.get(path, headers=headers).status_code == 200


def test_session_hash_expiry_and_logout(hr):
    client, records, factory, config, headers, login = hr
    with factory() as db:
        row = db.scalar(select(HRSession).where(HRSession.token_hash == digest(login["token"])))
        assert row and row.token_hash != login["token"]
    assert client.get("/candidate/interview", headers=headers).status_code == 401
    assert (
        client.post(
            "/hr/session", json={"email": config.hr_demo_email, "password": "wrong"}
        ).status_code
        == 401
    )
    assert client.delete("/hr/session", headers=headers).status_code == 204
    assert client.get("/hr/session", headers=headers).status_code == 401


def test_expired_session(hr):
    client, _, factory, _, headers, login = hr
    with factory() as db, db.begin():
        row = db.scalar(select(HRSession).where(HRSession.token_hash == digest(login["token"])))
        row.created_at -= timedelta(days=2)
        row.expires_at = row.created_at + timedelta(hours=1)
    assert client.get("/hr/roles", headers=headers).status_code == 401


def test_review_override_audit_and_retry(hr):
    client, records, factory, _, headers, login = hr
    receipt = client.post(
        endpoint(records[0]), headers=auth(records[0], "text"), json={"text": "Specific example"}
    )
    assert receipt.status_code == 201
    response = client.get(f"/hr/applications/{records[0]['application_id']}", headers=headers)
    assert response.status_code == 200, response.text
    answer = response.json()["questions"][0]["revisions"][0]
    aid, jid = answer["id"], answer["job"]["id"]
    assert answer["effective_score"] is None and answer["suggestion"] is None
    assert response.json()["questions"][0]["rubric"]["4"] == "Measured"
    for score, reason in [(3, "Clear evidence"), (4, "Additional detail reviewed")]:
        result = client.post(
            f"/hr/answers/{aid}/overrides", headers=headers, json={"score": score, "reason": reason}
        )
        assert result.status_code == 201, result.text
        assert result.json()["actor_id"] == login["user"]["id"]
    updated = client.get(f"/hr/answers/{aid}", headers=headers).json()
    assert updated["effective_score"] == 4 and updated["effective_score_source"] == "hr"
    assert len(updated["overrides"]) == 2 and updated["job"]["status"] == "queued"
    with factory() as db, db.begin():
        job = db.get(ScoringJob, jid)
        job.status, job.error_code, job.error_message = (
            "failed",
            "test_only",
            "Isolated test failure",
        )
        job.attempts = 3
    result = client.post(f"/hr/jobs/{jid}/retry", headers=headers)
    assert result.status_code == 200 and result.json()["requeued"]
    assert result.json()["job"]["attempts"] == 3
    assert client.post(f"/hr/jobs/{jid}/retry", headers=headers).json()["requeued"] is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Suggestion)) == 0
        assert db.scalar(select(func.count()).select_from(Override)) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"score": 0, "reason": "x"},
        {"score": True, "reason": "x"},
        {"score": 2, "reason": " "},
        {"score": 2, "reason": "x", "actor_id": str(uuid4())},
    ],
)
def test_invalid_override(hr, body):
    client, _, _, _, headers, _ = hr
    assert (
        client.post(f"/hr/answers/{uuid4()}/overrides", headers=headers, json=body).status_code
        == 422
    )


def test_private_audio_and_containment(hr):
    client, records, factory, config, headers, _ = hr
    result = client.post(
        endpoint(records[0], kind="audio"),
        headers=auth(records[0], "audio"),
        files={"file": ("x.wav", wav_bytes(), "audio/wav")},
    )
    assert result.status_code == 201
    review = client.get(f"/hr/applications/{records[0]['application_id']}", headers=headers).json()
    answer = review["questions"][0]["revisions"][0]
    assert "audio_path" not in answer
    url = answer["audio_url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(records[0])).status_code == 401
    audio = client.get(url, headers=headers)
    assert audio.status_code == 200 and audio.content == wav_bytes()
    assert audio.headers["cache-control"] == "no-store"
    assert client.post(f"/hr/jobs/{answer['job']['id']}/retry", headers=headers).status_code == 409
    with factory() as db, db.begin():
        db.get(Answer, answer["id"]).audio_path = "/etc/passwd"
    assert client.get(url, headers=headers).status_code == 404


def test_invitation_create_revoke_and_candidate_duplicates(hr):
    client, records, _, _, headers, _ = hr
    result = client.post(
        "/hr/candidates",
        headers=headers,
        json={
            "name": "New Candidate",
            "email": "new@example.test",
            "interview_id": str(records[0]["interview_id"]),
        },
    )
    assert result.status_code == 201, result.text
    aid = result.json()["id"]
    assert (
        client.post(
            "/hr/candidates",
            headers=headers,
            json={
                "name": "New Candidate",
                "email": "NEW@example.test",
                "interview_id": str(records[0]["interview_id"]),
            },
        ).status_code
        == 409
    )
    invitation = client.post(
        f"/hr/applications/{aid}/invitations", headers=headers, json={"days": 7}
    )
    assert invitation.status_code == 201, invitation.text
    data = invitation.json()
    candidate_headers = {"Authorization": "Bearer " + data["token"]}
    assert client.get("/candidate/interview", headers=candidate_headers).status_code == 200
    listing = client.get(f"/hr/applications/{aid}/invitations", headers=headers)
    assert "token" not in listing.json()[0] and "token_hash" not in listing.text
    assert client.delete(f"/hr/invitations/{data['id']}", headers=headers).status_code == 204
    assert client.get("/candidate/interview", headers=candidate_headers).status_code == 401


def test_pagination_and_not_found(hr):
    client, _, _, _, headers, _ = hr
    assert len(client.get("/hr/candidates?limit=1", headers=headers).json()) == 1
    assert client.get("/hr/jobs?limit=101", headers=headers).status_code == 422
    assert client.get("/hr/jobs?status=running", headers=headers).status_code == 422
    assert client.get(f"/hr/applications/{uuid4()}", headers=headers).status_code == 404
    assert client.post(f"/hr/jobs/{uuid4()}/retry", headers=headers).status_code == 404
    assert client.get("/hr/status", headers=headers).json()["live_scoring_configured"] is False


def test_override_preserves_model_suggestion_and_blocks_scored_retry(hr):
    client, records, factory, _, headers, _ = hr
    client.post(
        endpoint(records[0]),
        headers=auth(records[0], "scored"),
        json={"text": "Isolated model fixture"},
    )
    with factory() as db, db.begin():
        answer = db.scalar(
            select(Answer).where(Answer.application_id == records[0]["application_id"])
        )
        job = db.scalar(select(ScoringJob).where(ScoringJob.answer_id == answer.id))
        job.status = "scored"
        db.add(
            Suggestion(
                answer_id=answer.id,
                job_id=job.id,
                score=2,
                reason="Labelled isolated test fixture",
                model="test-only",
                response_id="test-only",
                rubric_version="test",
                prompt_version="test",
            )
        )
        aid, jid = answer.id, job.id
    assert (
        client.post(
            f"/hr/answers/{aid}/overrides",
            headers=headers,
            json={"score": 3, "reason": "HR evidence review"},
        ).status_code
        == 201
    )
    result = client.get(f"/hr/answers/{aid}", headers=headers).json()
    assert result["suggestion"]["score"] == 2 and result["effective_score"] == 3
    assert result["suggestion"]["reason"] == "Labelled isolated test fixture"
    assert client.post(f"/hr/jobs/{jid}/retry", headers=headers).status_code == 409


def test_inactive_user_and_unconfigured_login(hr):
    from talent_api.models import HRUser

    client, _, factory, config, headers, login = hr
    with factory() as db, db.begin():
        db.get(HRUser, login["user"]["id"]).is_active = False
    assert client.get("/hr/roles", headers=headers).status_code == 401
    assert (
        client.post(
            "/hr/session", json={"email": config.hr_demo_email, "password": "local-test-password"}
        ).status_code
        == 403
    )
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    assert (
        client.post(
            "/hr/session", json={"email": config.hr_demo_email, "password": "any"}
        ).status_code
        == 503
    )
    result = client.post(
        "/hr/session", json={"email": config.hr_demo_email, "password": {"secret": "must-not-echo"}}
    )
    assert result.status_code == 422 and "must-not-echo" not in result.text


def test_candidate_worker_hr_round_trip_without_live_provider(hr):
    """Exercise service boundaries together; fake scores exist only in rolled-back tests."""
    from test_worker import FakeScorer

    from talent_api.scoring import ScoringError
    from talent_api.worker import process_one

    client, records, factory, config, headers, _ = hr
    record = records[0]
    payload = {"text": "I measured report errors and added reconciliation checks."}
    receipt = client.post(endpoint(record), headers=auth(record, "round-trip"), json=payload)
    assert receipt.status_code == 201
    duplicate = client.post(endpoint(record), headers=auth(record, "round-trip"), json=payload)
    assert duplicate.status_code == 200 and duplicate.json() == receipt.json()

    def review():
        response = client.get(f"/hr/applications/{record['application_id']}", headers=headers)
        assert response.status_code == 200
        return response.json()["questions"][0]["revisions"][0]

    failed = FakeScorer(error=ScoringError("test_provider_failure", "Test provider unavailable"))
    assert process_one(failed, factory, config).status == "failed"
    answer = review()
    assert answer["suggestion"] is None and answer["effective_score"] is None
    assert answer["job"]["status"] == "failed"
    job_id = answer["job"]["id"]
    assert client.post(f"/hr/jobs/{job_id}/retry", headers=headers).json()["requeued"]
    assert not client.post(f"/hr/jobs/{job_id}/retry", headers=headers).json()["requeued"]

    scorer = FakeScorer()
    assert process_one(scorer, factory, config).status == "scored"
    assert process_one(scorer, factory, config) is None
    answer = review()
    assert answer["job"]["id"] == job_id and answer["job"]["status"] == "scored"
    assert answer["suggestion"]["score"] == 2 and answer["effective_score"] == 2
    original = answer["suggestion"]
    override = client.post(
        f"/hr/answers/{answer['id']}/overrides",
        headers=headers,
        json={"score": 3, "reason": "Synthetic integration check: additional evidence reviewed"},
    )
    assert override.status_code == 201
    answer = review()
    assert answer["effective_score"] == 3 and answer["suggestion"] == original
    assert len(answer["overrides"]) == 1

    # A new request/client observes persisted progress, without any scoring metadata.
    progress = client.get("/candidate/progress", headers=auth(record))
    assert progress.status_code == 200 and progress.json()["answered_count"] == 1
    public = client.get("/candidate/interview", headers=auth(record)).text
    for private_field in ['"suggestion"', '"rubric"', '"effective_score"', '"overrides"']:
        assert private_field not in public
    assert client.get(f"/hr/answers/{answer['id']}", headers=auth(record)).status_code == 401

    upload = client.post(
        endpoint(record, number=2, kind="audio"),
        headers=auth(record, "round-trip-audio"),
        files={"file": ("answer.wav", wav_bytes(), "audio/wav")},
    )
    assert upload.status_code == 201
    application = client.get(f"/hr/applications/{record['application_id']}", headers=headers).json()
    audio = application["questions"][1]["revisions"][0]
    assert audio["job"]["status"] == "needs a person" and audio["suggestion"] is None
    assert client.get(audio["audio_url"], headers=headers).content == wav_bytes()
    assert client.get(audio["audio_url"], headers=auth(record)).status_code == 401
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Suggestion)) == 1
        assert session.scalar(select(func.count()).select_from(ScoringJob)) == 2
    assert client.delete("/hr/session", headers=headers).status_code == 204
    assert client.get("/hr/jobs", headers=headers).status_code == 401
