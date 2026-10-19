"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";
import Check from "./check-icon";
export default function CompletionSummary({
  state,
}: {
  state: Pick<CandidateWorkspace, "interview" | "heading">;
}) {
  const { interview, heading } = state;
  if (!interview) return null;
  return (
    <div className="state-card complete-card">
      <Check large />
      <span className="eyebrow">6 OF 6 · ALL RECEIVED</span>
      <h1 ref={heading} tabIndex={-1}>
        Thank you for sharing your story.
      </h1>
      <p>
        Your interview answers are safely received. HR will review them and
        follow up with you.
      </p>
      <div className="completion-list">
        {interview.progress.questions.map((q, i) => (
          <div key={q.question_id}>
            <Check />
            <strong>Question {i + 1}</strong>
            <span>
              {q.receipt?.input_kind === "audio" ? "Audio" : "Written"} answer
              received
            </span>
          </div>
        ))}
      </div>
      <details className="saved-receipts">
        <summary>View your submission receipts</summary>
        <ul>
          {interview.progress.questions.map((q, i) => (
            <li key={q.question_id}>
              Question {i + 1}
              <code>{q.receipt?.receipt}</code>
            </li>
          ))}
        </ul>
      </details>
      <p className="muted small">
        You can close this page. This personal link will continue to show your
        saved confirmation while it remains valid.
      </p>
    </div>
  );
}
