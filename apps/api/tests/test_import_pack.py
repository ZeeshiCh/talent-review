"""Synthetic fixtures test import behavior without model calls or reference grades."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from talent_api.db import engine
from talent_api.import_pack import ImportProblem, import_pack, read_pack, verify_import
from talent_api.models import Answer, Candidate, Question, Role, ScoringJob, Suggestion

DB = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1")
ROLES = [
    "Backend Engineer",
    "Sales Executive",
    "Customer Success Associate",
    "Marketing Coordinator",
    "Finance Analyst",
]


@pytest.fixture
def source(tmp_path):
    pack = tmp_path / "pack"
    (pack / "answers").mkdir(parents=True)
    (pack / "questions.md").write_text(
        "Open roles: "
        + ", ".join(ROLES)
        + ".\n\n"
        + "\n\n".join(
            f"## Q{i}. Question {i}?\n\n" + "\n".join(f"- **{j}:** Guide {j}" for j in range(1, 5))
            for i in range(1, 7)
        )
    )
    (pack / "pipeline_log.csv").write_text(
        "candidate_id,candidate_name,candidate_email,role\nC1,Test Person,one@example.test,Backend Engineer\nC2,Other Person,two@example.test,Sales Executive\nC999,Unrelated,unused@example.test,Finance Analyst\n"
    )
    rows = [
        {
            "answer_id": "A001",
            "candidate_id": "C1",
            "role": ROLES[0],
            "question_id": "Q1",
            "submitted_at": "2026-09-14T10:00:00",
            "duration_seconds": 20,
            "transcript": "Original evidence",
        },
        {
            "answer_id": "A002",
            "candidate_id": "C1",
            "role": ROLES[0],
            "question_id": "Q1",
            "submitted_at": "2026-09-14T11:00:00",
            "duration_seconds": 30,
            "transcript": "Revised evidence",
        },
        {
            "answer_id": "A003",
            "candidate_id": "C1",
            "role": ROLES[0],
            "question_id": "Q2",
            "submitted_at": "2026-09-14T12:00:00",
            "duration_seconds": 0,
            "transcript": "",
        },
        {
            "answer_id": "A004",
            "candidate_id": "C2",
            "role": ROLES[1],
            "question_id": "Q1",
            "submitted_at": "2026-09-14T12:00:00",
            "duration_seconds": 30,
            "transcript": None,
            "audio_file": "A004.m4a",
        },
    ]
    for row in rows:
        (pack / "answers" / f"{row['answer_id']}.json").write_text(json.dumps(row))
    # A minimal synthetic M4A-like container fixture, not a claimed playable recording.
    (pack / "answers/A004.m4a").write_bytes(b"\x00\x00\x00\x18ftypM4A test fixture")
    return pack


def edit(source, answer_id, **changes):
    path = source / "answers" / f"{answer_id}.json"
    row = json.loads(path.read_text())
    row.update(changes)
    path.write_text(json.dumps(row))


def test_parser_retains_source_and_excludes_unrelated_metadata(source):
    pack = read_pack(source)
    assert len(pack.questions) == 6 and len(pack.roles) == 5
    assert set(pack.candidates) == {"C1", "C2"}
    assert [a.kind for a in pack.answers] == ["text", "text", "missing", "audio"]
    assert pack.answers[0].source.submitted_at == "2026-09-14T10:00:00"
    # Import does not read or require HR scores, outcomes, inbox, or time logs.
    assert not (source / "hr_reference_scores.csv").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"question_id": "Q7"},
        {"role": "Unknown"},
        {"duration_seconds": -1},
        {"submitted_at": "not-a-date"},
        {"candidate_id": "C9999"},
        {"transcript": "Both audio and text", "audio_file": "A001.m4a"},
    ],
)
def test_invalid_source_rejected_before_writes(source, changes):
    edit(source, "A001", **changes)
    with pytest.raises(ImportProblem):
        read_pack(source)


@pytest.mark.parametrize("audio_file", ["../private.m4a", "A999.m4a", "/tmp/private.m4a"])
def test_audio_traversal_and_wrong_names_rejected(source, audio_file):
    edit(source, "A004", audio_file=audio_file)
    with pytest.raises(ImportProblem, match="Unsafe or mismatched"):
        read_pack(source)


def test_missing_audio_rejected(source):
    (source / "answers/A004.m4a").unlink()
    with pytest.raises(ImportProblem, match="Missing, empty, or oversized"):
        read_pack(source)


def test_duplicate_question_or_rubric_rejected(source):
    path = source / "questions.md"
    path.write_text(path.read_text().replace("- **4:** Guide 4", "- **3:** Duplicate"))
    with pytest.raises(ImportProblem, match="rubric"):
        read_pack(source)


def test_repeated_payload_with_different_source_id_is_explicit_conflict(source):
    edit(source, "A002", transcript="Original evidence")
    with pytest.raises(ImportProblem, match="Repeated content"):
        read_pack(source)


def test_candidate_role_mismatch_rejected(source):
    edit(source, "A001", role=ROLES[1])
    with pytest.raises(ImportProblem, match="role mismatch"):
        read_pack(source)


@DB
def test_repeat_import_preserves_receipts_revisions_and_scored_jobs(db, source, tmp_path):
    pack = read_pack(source)
    audio_root = tmp_path / "private"
    first = import_pack(db, pack, audio_root)
    assert first["verified"]["question_rows"] == 30
    assert first["verified"]["current_answers"] == 3
    assert first["verified"]["superseded_answers"] == 1
    assert first["verified"]["job_statuses"] == {"queued": 2, "needs a person": 2}
    # Reading creates a transaction; finish it before invoking the transaction-owning importer.
    with db.begin():
        rows = db.scalars(select(Answer)).all()
        original = {a.source_id: (a.id, a.receipt) for a in rows}
        assert [
            a.source_id
            for a in rows
            if a.is_current
            and a.question_id == next(a.question_id for a in rows if a.source_id == "A001")
        ] == ["A002"]
        answer = next(a for a in rows if a.source_id == "A002")
        job = db.scalar(select(ScoringJob).where(ScoringJob.answer_id == answer.id))
        job.status, job.attempts = "scored", 1
        db.add(
            Suggestion(
                answer_id=answer.id,
                job_id=job.id,
                score=3,
                reason="Test fixture only",
                model="fake-for-test",
                response_id="resp-test",
                rubric_version=pack.rubric_version,
                prompt_version="test",
            )
        )
    second = import_pack(db, pack, audio_root)
    assert not any(k.endswith("_created") for k in second["changes"])
    with db.begin():
        assert {a.source_id: (a.id, a.receipt) for a in db.scalars(select(Answer))} == original
        assert db.scalar(select(func.count()).select_from(Suggestion)) == 1
        assert (
            db.scalar(select(ScoringJob.status).where(ScoringJob.answer_id == answer.id))
            == "scored"
        )
    assert len(list(audio_root.glob("*.m4a"))) == 1
    assert len(list(audio_root.glob(".import-*"))) == 0


@DB
def test_input_order_does_not_choose_current_revision(db, source, tmp_path):
    pack = read_pack(source)
    import_pack(db, replace(pack, answers=list(reversed(pack.answers))), tmp_path / "private")
    with db.begin():
        assert db.scalar(select(Answer.is_current).where(Answer.source_id == "A002")) is True
        assert db.scalar(select(Answer.is_current).where(Answer.source_id == "A001")) is False


@DB
def test_mutated_source_rolls_back_and_never_overwrites_existing_answer(db, source, tmp_path):
    pack = read_pack(source)
    audio_root = tmp_path / "private"
    import_pack(db, pack, audio_root)
    edit(source, "A001", transcript="Changed under the same source ID")
    with pytest.raises(ImportProblem, match="Source conflict"):
        import_pack(db, read_pack(source), audio_root)
    with db.begin():
        assert (
            db.scalar(select(Answer.text_content).where(Answer.source_id == "A001"))
            == "Original evidence"
        )
        assert db.scalar(select(func.count()).select_from(Answer)) == 4


@DB
def test_late_conflict_rolls_back_every_database_write(db, source, tmp_path):
    # Seed a conflicting candidate. The importer creates roles and questions first;
    # none of those inserts should remain after this later failure.
    with db.begin():
        db.add(Candidate(source_id="C1", name="Existing identity", email="existing@example.test"))
    with pytest.raises(ImportProblem, match="Source conflict"):
        import_pack(db, read_pack(source), tmp_path / "private")
    with db.begin():
        assert db.scalar(select(func.count()).select_from(Role)) == 0
        assert db.scalar(select(func.count()).select_from(Question)) == 0
        assert db.scalar(select(func.count()).select_from(Answer)) == 0


@DB
def test_incremental_import_keeps_later_revision_current(db, source, tmp_path):
    pack = read_pack(source)
    only_latest = replace(pack, answers=[a for a in pack.answers if a.source.answer_id != "A001"])
    import_pack(db, only_latest, tmp_path / "private")
    report = import_pack(db, pack, tmp_path / "private")
    assert report["verified"]["answer_revisions"] == 4
    with db.begin():
        assert db.scalar(select(Answer.is_current).where(Answer.source_id == "A002")) is True


@DB
def test_verify_only_detects_mutated_rubrics(db, source, tmp_path):
    pack = read_pack(source)
    root = tmp_path / "private"
    import_pack(db, pack, root)
    with db.begin():
        q = db.scalar(select(Question).limit(1))
        q.prompt = "Mutated question"
    with db.begin():
        with pytest.raises(ImportProblem, match="question or rubric"):
            verify_import(db, pack, root)


@DB
def test_two_concurrent_imports_create_one_copy(source, tmp_path):
    # This test requires committed state for two connections. Only the randomly named
    # disposable test schema is created/dropped; public application tables are untouched.
    schema = "test_import_" + uuid4().hex
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
        pack = read_pack(source)

        def run():
            with engine.begin() as conn:
                conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
                    return import_pack(session, pack, tmp_path / "private")

        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda _: run(), range(2)))
        assert sorted(r["changes"].get("answers_created", 0) for r in reports) == [0, 4]
        with engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            assert conn.scalar(select(func.count()).select_from(Answer)) == 4
            assert conn.scalar(select(func.count()).select_from(ScoringJob)) == 4
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
