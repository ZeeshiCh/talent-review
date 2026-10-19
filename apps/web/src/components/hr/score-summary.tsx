"use client";
import { Answer } from "../../lib/hr-api";
export default function ScoreSummary({ answer }: { answer: Answer }) {
  return (
    <div className="hr-score-grid">
      <div>
        <span className="eyebrow">MODEL SUGGESTION</span>
        <strong>
          {answer.suggestion
            ? `${answer.suggestion.score} / 4`
            : "Not available"}
        </strong>
        <p>{answer.suggestion?.reason || "No model score has been stored."}</p>
        {answer.suggestion && (
          <small>
            {answer.suggestion.model} · rubric{" "}
            {answer.suggestion.rubric_version}
          </small>
        )}
      </div>
      <div>
        <span className="eyebrow">EFFECTIVE SCORE</span>
        <strong>
          {answer.effective_score === null
            ? "Unscored"
            : `${answer.effective_score} / 4`}
        </strong>
        <p>
          {answer.effective_score_source === "hr"
            ? "HR override"
            : answer.effective_score_source === "model"
              ? "Model suggestion · awaiting HR judgment"
              : "Awaiting scoring or human review"}
        </p>
      </div>
    </div>
  );
}
