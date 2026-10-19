"""Validated, atomic, repeatable import of a local synthetic interview data pack.

No model calls, reference grades, authentication tokens, or hiring decisions are imported.
"""

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import ROOT
from .db import SessionLocal
from .models import Answer, Application, Candidate, Interview, Question, Role, ScoringJob
from .storage import StorageProblem, digest, store_audio

DATASET = "business-systems-v1.1.0"
NAMESPACE = UUID("1b0260ec-1555-4a02-a91d-8e663efc7205")
IMPORT_LOCK = 584729103621
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class ImportProblem(StorageProblem):
    """Safe import validation/conflict message; transaction must not partially commit."""


class RawAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer_id: str = Field(pattern=r"^A[0-9]{3}$")
    candidate_id: str = Field(pattern=r"^C[0-9]+$")
    role: str = Field(min_length=1, max_length=200)
    question_id: str = Field(pattern=r"^Q[1-6]$")
    submitted_at: str = Field(min_length=1, max_length=100)
    duration_seconds: int = Field(ge=0)
    transcript: str | None = Field(max_length=50000)
    audio_file: str | None = None


@dataclass(frozen=True)
class PackQuestion:
    source_id: str
    position: int
    prompt: str
    rubric: dict[str, str]


@dataclass(frozen=True)
class PackAnswer:
    source: RawAnswer
    kind: str
    content_hash: str
    audio: bytes | None


@dataclass(frozen=True)
class Pack:
    roles: list[str]
    questions: list[PackQuestion]
    rubric_version: str
    candidates: dict[str, dict[str, str]]
    answers: list[PackAnswer]


def identity(label: str) -> UUID:
    return uuid5(NAMESPACE, f"{DATASET}:{label}")


def source_order(timestamp: str, source_id: str) -> tuple[datetime, str]:
    """Compare source dates as supplied. Never silently assign them a timezone."""
    try:
        return datetime.fromisoformat(timestamp), source_id
    except ValueError:
        raise ImportProblem(f"Invalid source timestamp for {source_id}") from None


def read_pack(pack_dir: Path) -> Pack:
    """Validate all source content before writing files or database rows."""
    try:
        question_text = (pack_dir / "questions.md").read_text(encoding="utf-8")
        role_match = re.search(r"^Open roles: (.+)\.$", question_text, flags=re.M)
        if not role_match:
            raise ImportProblem("questions.md must list the open roles")
        roles = [value.strip() for value in role_match.group(1).split(",")]
        if len(roles) != 5 or len(set(roles)) != 5 or any(not r or len(r) > 200 for r in roles):
            raise ImportProblem("Expected five distinct open roles")
        sections = re.split(r"^## (Q[1-6])\. ", question_text, flags=re.M)
        questions = []
        for i in range(1, len(sections), 2):
            qid, section = sections[i : i + 2]
            rubric_rows = re.findall(r"^- \*\*([1-4]):\*\* (.+)$", section, flags=re.M)
            rubric = dict(rubric_rows)
            prompt = section.splitlines()[0].strip()
            if (
                len(rubric_rows) != 4
                or set(rubric) != {"1", "2", "3", "4"}
                or not prompt
                or any(not v.strip() for v in rubric.values())
            ):
                raise ImportProblem(f"Missing/duplicate rubric levels or question text for {qid}")
            questions.append(PackQuestion(qid, int(qid[1:]), prompt, rubric))
        if len(questions) != 6 or {q.source_id for q in questions} != {
            f"Q{i}" for i in range(1, 7)
        }:
            raise ImportProblem("Expected exactly six distinct questions Q1–Q6")
        questions.sort(key=lambda q: q.position)
        # Hash the actual rubric content; reference grades never participate.
        rubric_version = f"{DATASET}:{digest(question_text.encode())[:12]}"
        paths = sorted((pack_dir / "answers").glob("*.json"))
        if not paths:
            raise ImportProblem("No answer JSON files found")
        answers = []
        source_ids: set[str] = set()
        payloads: set[tuple[str, str, str, str]] = set()
        for path in paths:
            try:
                raw = RawAnswer.model_validate_json(path.read_bytes())
            except ValidationError:
                raise ImportProblem(f"Invalid answer record: {path.name}") from None
            if path.stem != raw.answer_id or raw.answer_id in source_ids:
                raise ImportProblem(f"Duplicate or mismatched source answer ID: {path.name}")
            source_ids.add(raw.answer_id)
            source_order(raw.submitted_at, raw.answer_id)
            if raw.role not in roles:
                raise ImportProblem(f"Unknown role in {raw.answer_id}")
            audio = None
            if raw.audio_file:
                if raw.transcript and raw.transcript.strip():
                    raise ImportProblem(f"Ambiguous text and audio input in {raw.answer_id}")
                if raw.audio_file != f"{raw.answer_id}.m4a":
                    raise ImportProblem(f"Unsafe or mismatched audio path in {raw.answer_id}")
                file = pack_dir / "answers" / raw.audio_file
                if file.is_symlink() or not file.resolve().is_relative_to(
                    (pack_dir / "answers").resolve()
                ):
                    raise ImportProblem(f"Unsafe audio path in {raw.answer_id}")
                if not file.is_file() or not 0 < file.stat().st_size <= MAX_AUDIO_BYTES:
                    raise ImportProblem(f"Missing, empty, or oversized audio for {raw.answer_id}")
                audio = file.read_bytes()
                if len(audio) > MAX_AUDIO_BYTES or audio[4:8] != b"ftyp":
                    raise ImportProblem(f"Invalid M4A container for {raw.answer_id}")
                kind, body = "audio", digest(audio)
            elif raw.transcript and raw.transcript.strip():
                kind, body = "text", raw.transcript
            else:
                kind, body = "missing", ""
            content_hash = digest(
                json.dumps(
                    {"kind": kind, "body": body}, sort_keys=True, ensure_ascii=False
                ).encode()
            )
            key = raw.candidate_id, raw.role, raw.question_id, content_hash
            if key in payloads:
                # There is no source-alias table: do not silently lose a second source ID.
                raise ImportProblem(f"Repeated content under different source IDs: {raw.answer_id}")
            payloads.add(key)
            answers.append(PackAnswer(raw, kind, content_hash, audio))
        required = {a.source.candidate_id for a in answers}
        candidates = {}
        with (pack_dir / "pipeline_log.csv").open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fields = {"candidate_id", "candidate_name", "candidate_email", "role"}
            if not fields <= set(reader.fieldnames or []):
                raise ImportProblem("Pipeline metadata is missing candidate identity columns")
            for row in reader:
                cid = row["candidate_id"]
                if cid not in required:
                    continue
                if cid in candidates:
                    raise ImportProblem(f"Duplicate pipeline candidate ID: {cid}")
                if any(not (row.get(k) or "").strip() for k in fields):
                    raise ImportProblem(f"Incomplete candidate identity: {cid}")
                if len(row["candidate_name"]) > 200 or len(row["candidate_email"]) > 320:
                    raise ImportProblem(f"Oversized candidate identity: {cid}")
                candidates[cid] = {k: row[k] for k in fields}
        if set(candidates) != required:
            raise ImportProblem("Some answer candidates are missing from pipeline metadata")
        for answer in answers:
            if candidates[answer.source.candidate_id]["role"] != answer.source.role:
                raise ImportProblem(f"Candidate role mismatch for {answer.source.answer_id}")
        # Detect incompatible naive/aware timestamps before any database writes.
        groups: dict[tuple[str, str, str], list[PackAnswer]] = {}
        for a in answers:
            groups.setdefault(
                (a.source.candidate_id, a.source.role, a.source.question_id), []
            ).append(a)
        for group in groups.values():
            try:
                sorted(group, key=lambda a: source_order(a.source.submitted_at, a.source.answer_id))
            except TypeError:
                raise ImportProblem(
                    "Cannot compare mixed timezone-aware and naive source timestamps"
                ) from None
        return Pack(roles, questions, rubric_version, candidates, answers)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ImportProblem(f"Cannot read data pack ({type(exc).__name__})") from None


def ensure(session: Session, entity: type, lookup: dict, values: dict, counts: Counter):
    """Create or verify an immutable source record; never overwrite changed source data."""
    row = session.scalar(select(entity).filter_by(**lookup))
    if row is None:
        row = entity(**{**lookup, **values})
        session.add(row)
        session.flush()
        counts[f"{entity.__tablename__}_created"] += 1
    elif any(getattr(row, key) != value for key, value in values.items()):
        raise ImportProblem(
            f"Source conflict in {entity.__tablename__}; existing data was not overwritten"
        )
    else:
        counts[f"{entity.__tablename__}_reused"] += 1
    return row


def import_pack(session: Session, pack: Pack, audio_root: Path) -> dict:
    """Own one transaction. Caller must supply a fresh session, with no active transaction.

    Imports serialize on a transaction-scoped advisory lock. Constraint violations or
    source conflicts roll back every database write. Private blobs may remain after a
    failed transaction; they are immutable and reused on the next successful import.
    """
    counts: Counter = Counter()
    with session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
        interviews, questions, applications = {}, {}, {}
        for role_name in pack.roles:
            role = ensure(session, Role, {"name": role_name}, {}, counts)
            interview = ensure(
                session,
                Interview,
                {"id": identity(f"interview:{role_name}")},
                {"role_id": role.id, "title": "Candidate interview — " + DATASET},
                counts,
            )
            interviews[role_name] = interview
            for q in pack.questions:
                questions[role_name, q.source_id] = ensure(
                    session,
                    Question,
                    {"interview_id": interview.id, "source_id": q.source_id},
                    {
                        "position": q.position,
                        "prompt": q.prompt,
                        "rubric_version": pack.rubric_version,
                        **{f"rubric_{level}": guide for level, guide in q.rubric.items()},
                    },
                    counts,
                )
        for cid, meta in sorted(pack.candidates.items()):
            candidate = ensure(
                session,
                Candidate,
                {"source_id": cid},
                {"name": meta["candidate_name"], "email": meta["candidate_email"]},
                counts,
            )
            applications[cid] = ensure(
                session,
                Application,
                {"candidate_id": candidate.id, "interview_id": interviews[meta["role"]].id},
                {},
                counts,
            )
        affected = set()
        for item in pack.answers:
            raw = item.source
            application, question = (
                applications[raw.candidate_id],
                questions[raw.role, raw.question_id],
            )
            audio_path = store_audio(audio_root, item.audio) if item.audio is not None else None
            values = {
                "application_id": application.id,
                "interview_id": interviews[raw.role].id,
                "question_id": question.id,
                "source_submitted_at": raw.submitted_at,
                "input_kind": item.kind,
                "content_hash": item.content_hash,
                "duration_seconds": raw.duration_seconds,
                "text_content": raw.transcript if item.kind != "audio" else None,
                "audio_path": audio_path,
                "audio_mime_type": "audio/mp4" if item.audio is not None else None,
                "audio_size_bytes": len(item.audio) if item.audio is not None else None,
            }
            existing = session.scalar(select(Answer).where(Answer.source_id == raw.answer_id))
            if existing is None:
                # Do not silently collapse a distinct source ID into an existing answer.
                duplicate = session.scalar(
                    select(Answer.id).where(
                        Answer.application_id == application.id,
                        Answer.question_id == question.id,
                        Answer.content_hash == item.content_hash,
                    )
                )
                if duplicate is not None:
                    raise ImportProblem(
                        f"Duplicate content conflicts with source ID {raw.answer_id}"
                    )
            # New revisions start noncurrent so order-independent imports do not conflict.
            answer = (
                ensure(session, Answer, {"source_id": raw.answer_id}, values, counts)
                if existing
                else None
            )
            if answer is None:
                answer = Answer(source_id=raw.answer_id, is_current=False, **values)
                session.add(answer)
                session.flush()
                counts["answers_created"] += 1
            affected.add((application.id, question.id))
            job = session.scalar(select(ScoringJob).where(ScoringJob.answer_id == answer.id))
            if job is None:
                reason = (
                    "Audio transcription is not implemented; HR review required."
                    if item.kind == "audio"
                    else "Imported answer has no content; HR review required."
                )
                session.add(
                    ScoringJob(
                        answer_id=answer.id,
                        status="queued" if item.kind == "text" else "needs a person",
                        review_reason=None if item.kind == "text" else reason,
                    )
                )
                session.flush()
                counts["scoring_jobs_created"] += 1
            else:
                # Preserve completed/failed jobs and suggestions on every rerun.
                counts["scoring_jobs_reused"] += 1
        for application_id, question_id in sorted(affected):
            # Lock participation before choosing a current revision. Candidate services
            # must use the same application lock when modifying this answer slot.
            session.scalar(
                select(Application).where(Application.id == application_id).with_for_update()
            )
            rows = session.scalars(
                select(Answer)
                .where(Answer.application_id == application_id, Answer.question_id == question_id)
                .with_for_update()
            ).all()
            if any(not row.source_id or not row.source_submitted_at for row in rows):
                raise ImportProblem(
                    "An answer slot contains unmanaged submissions; import will not replace them"
                )
            try:
                winner = max(
                    rows, key=lambda row: source_order(row.source_submitted_at, row.source_id)
                )
            except TypeError:
                raise ImportProblem(
                    "Incompatible source timestamps in stored answer revisions"
                ) from None
            for row in rows:
                if row.is_current and row.id != winner.id:
                    row.is_current = False
            session.flush()  # Release old partial-index entry before selecting the winner.
            winner.is_current = True
        session.flush()
        report = verify_import(session, pack, audio_root)
    return {"dataset": DATASET, "changes": dict(sorted(counts.items())), "verified": report}


def verify_import(session: Session, pack: Pack, audio_root: Path) -> dict:
    """Verify every source mapping, private file, job, and current-revision selection."""
    for role_name in pack.roles:
        interview = session.get(Interview, identity(f"interview:{role_name}"))
        if interview is None:
            raise ImportProblem("Imported interview is missing")
        role = session.get(Role, interview.role_id)
        if role is None or role.name != role_name:
            raise ImportProblem("Imported interview role does not match")
        stored = session.scalars(
            select(Question).where(Question.interview_id == interview.id)
        ).all()
        if len(stored) != len(pack.questions):
            raise ImportProblem("Interview question count does not match source")
        by_question = {q.source_id: q for q in stored}
        for expected in pack.questions:
            q = by_question.get(expected.source_id)
            if (
                q is None
                or q.position != expected.position
                or q.prompt != expected.prompt
                or q.rubric_version != pack.rubric_version
                or any(getattr(q, f"rubric_{i}") != expected.rubric[str(i)] for i in range(1, 5))
            ):
                raise ImportProblem("Imported question or rubric does not match source")
    answers = session.scalars(
        select(Answer).where(Answer.source_id.in_([a.source.answer_id for a in pack.answers]))
    ).all()
    if len(answers) != len(pack.answers):
        raise ImportProblem("Imported answer count does not match source")
    by_source = {a.source_id: a for a in answers}
    states: Counter = Counter()
    current = 0
    for item in pack.answers:
        a = by_source[item.source.answer_id]
        candidate = session.scalar(
            select(Candidate)
            .join(Application, Application.candidate_id == Candidate.id)
            .where(Application.id == a.application_id)
        )
        q = session.get(Question, a.question_id)
        role = session.scalar(
            select(Role)
            .join(Interview, Interview.role_id == Role.id)
            .where(Interview.id == a.interview_id)
        )
        if (
            candidate.source_id != item.source.candidate_id
            or q.source_id != item.source.question_id
            or role.name != item.source.role
            or a.content_hash != item.content_hash
        ):
            raise ImportProblem("Imported source association does not match")
        meta = pack.candidates[item.source.candidate_id]
        if (
            candidate.name != meta["candidate_name"]
            or candidate.email != meta["candidate_email"]
            or a.source_submitted_at != item.source.submitted_at
            or a.duration_seconds != item.source.duration_seconds
            or a.input_kind != item.kind
            or a.text_content != (None if item.kind == "audio" else item.source.transcript)
        ):
            raise ImportProblem("Imported candidate or answer content does not match source")
        job = session.scalar(select(ScoringJob).where(ScoringJob.answer_id == a.id))
        if job is None:
            raise ImportProblem("Imported answer has no scoring job")
        states[job.status] += 1
        current += a.is_current
        if item.audio is not None:
            if (
                not a.audio_path
                or a.audio_mime_type != "audio/mp4"
                or a.audio_size_bytes != len(item.audio)
            ):
                raise ImportProblem("Imported audio metadata does not match source")
            file = Path(a.audio_path)
            if (
                file.is_symlink()
                or not file.resolve().is_relative_to(audio_root.resolve())
                or digest(file.read_bytes()) != digest(item.audio)
            ):
                raise ImportProblem("Imported audio does not match source")
    slots = {(a.application_id, a.question_id) for a in answers}
    for application_id, question_id in slots:
        revisions = session.scalars(
            select(Answer).where(
                Answer.application_id == application_id, Answer.question_id == question_id
            )
        ).all()
        expected = max(revisions, key=lambda a: source_order(a.source_submitted_at, a.source_id))
        if [a.id for a in revisions if a.is_current] != [expected.id]:
            raise ImportProblem("Current answer revision is not the latest source submission")
    return {
        "roles": len(pack.roles),
        "interviews": len(pack.roles),
        "question_definitions": len(pack.questions),
        "question_rows": len(pack.questions) * len(pack.roles),
        "candidates": len(pack.candidates),
        "applications": len(pack.candidates),
        "answer_revisions": len(answers),
        "current_answers": current,
        "superseded_answers": len(answers) - current,
        "answer_kinds": dict(Counter(a.kind for a in pack.answers)),
        "scoring_jobs": len(answers),
        "job_statuses": dict(states),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pack-dir",
        type=Path,
        required=True,
        help="Extracted directory with questions.md, answers/, and pipeline_log.csv",
    )
    parser.add_argument("--audio-dir", type=Path, default=ROOT / "var/uploads/imported-audio")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing data without changing database rows or files",
    )
    args = parser.parse_args()
    try:
        pack = read_pack(args.pack_dir)
        with SessionLocal() as session:
            if args.verify_only:
                report = {
                    "dataset": DATASET,
                    "verified": verify_import(session, pack, args.audio_dir),
                }
            else:
                report = import_pack(session, pack, args.audio_dir)
    except StorageProblem as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    except (SQLAlchemyError, OSError):
        parser.exit(
            1,
            "Import failed: database/storage operation did not complete; database changes were rolled back.\n",
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
