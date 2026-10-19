"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";
import Check from "./check-icon";
import AnswerForm from "./answer-form";
export default function QuestionPanel({
  state,
}: {
  state: CandidateWorkspace;
}) {
  const { current, heading, busy, refresh } = state;
  if (!current) return null;
  return (
    <>
      <div className="question-header">
        <span className="eyebrow">
          QUESTION {String(current.number).padStart(2, "0")} / 06
        </span>
        <span className="saved-badge">
          <Check />
          Progress saved
        </span>
      </div>
      <h1 className="question-title" ref={heading} tabIndex={-1}>
        {current.prompt}
      </h1>
      <p className="question-description">
        A specific example helps us understand your experience. Answer in the
        way that works best for you.
      </p>
      <AnswerForm state={state} />
      <div className="bottom-note">
        <span aria-hidden="true">ⓘ</span>
        <p>
          Accepted answers can’t be edited.{" "}
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Check saved progress
          </button>{" "}
          if a connection was interrupted.
        </p>
      </div>
    </>
  );
}
