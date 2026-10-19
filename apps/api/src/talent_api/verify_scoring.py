"""Explicit live smoke check: calls OpenAI; does not persist a score or run a job."""

import argparse
import json
import re
from pathlib import Path

from .config import ROOT
from .scoring import OpenAIScorer, ScoringError, ScoringInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=ROOT / "var/data-inspection/extracted")
    parser.add_argument("--answer-id", default="A001")
    args = parser.parse_args()
    if not re.fullmatch(r"A[0-9]{3}", args.answer_id):
        parser.error("answer ID must look like A001")
    try:
        record = json.loads((args.pack_dir / "answers" / f"{args.answer_id}.json").read_text())
        questions = (args.pack_dir / "questions.md").read_text()
        sections = re.split(r"^## (Q[1-6])\. ", questions, flags=re.M)
        matches = {sections[i]: sections[i + 1] for i in range(1, len(sections), 2)}
        section = matches[record["question_id"]]
        rubric = dict(re.findall(r"^- \*\*([1-4]):\*\* (.+)$", section, flags=re.M))
        answer = ScoringInput(
            question=section.splitlines()[0].strip(),
            rubric=rubric,
            rubric_version="data-pack-v1.1.0",
            answer_text=record.get("transcript") or "",
        )
        scorer = OpenAIScorer()
        try:
            result = scorer.score(answer)
        finally:
            scorer.client.close()
    except ScoringError as exc:
        parser.exit(1, f"Scoring check failed [{exc.code}]: {exc}\n")
    except (OSError, KeyError, ValueError):
        parser.exit(
            1,
            "Invalid/missing pack input. Supply a nonempty transcript and all four rubric levels.\n",
        )
    print(
        json.dumps(
            {
                "answer_id": args.answer_id,
                "model": result.model,
                "response_id": result.response_id,
                "rubric_version": result.rubric_version,
                "prompt_version": result.prompt_version,
                **result.output.model_dump(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
