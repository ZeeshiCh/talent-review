"use client";
import { HRWorkspaceState } from "../../hooks/use-hr-workspace";
import AnswerCard from "./answer-card";
export default function CandidateReview({
  state,
}: {
  state: Pick<
    HRWorkspaceState,
    "loading" | "applicationId" | "review" | "api" | "refresh" | "report"
  >;
}) {
  const { loading, applicationId, review, api, refresh, report } = state;
  return (
    <section className="hr-review" aria-label="Answer review">
      {loading && <p role="status">Loading review data…</p>}
      {!applicationId && !loading && (
        <div className="hr-empty">
          <span className="eyebrow">READY WHEN YOU ARE</span>
          <h2>Choose a candidate</h2>
          <p>
            Review each answer alongside its grading guide, suggestion, and
            history.
          </p>
        </div>
      )}
      {review && (
        <>
          <div className="hr-review-heading">
            <h2>{review.application.candidate.name}</h2>
            <p>
              {review.application.candidate.email} ·{" "}
              {review.application.answered_count} /{" "}
              {review.application.total_questions} answers received
            </p>
          </div>
          {review.questions.map((question) => (
            <section key={question.id} className="hr-question">
              <span className="eyebrow">QUESTION {question.number}</span>
              <h3>{question.prompt}</h3>
              <details className="hr-rubric">
                <summary>View grading guide</summary>
                {Object.entries(question.rubric).map(([score, description]) => (
                  <p key={score}>
                    <strong>{score} / 4</strong> {description}
                  </p>
                ))}
              </details>
              {question.revisions.length === 0 ? (
                <div className="hr-answer muted">No answer received yet.</div>
              ) : (
                [...question.revisions]
                  .sort((a, b) => Number(b.is_current) - Number(a.is_current))
                  .map((answer) => (
                    <AnswerCard
                      key={answer.id}
                      answer={answer}
                      api={api}
                      refresh={refresh}
                      onError={report}
                    />
                  ))
              )}
            </section>
          ))}
        </>
      )}
    </section>
  );
}
