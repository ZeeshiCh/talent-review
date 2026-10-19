"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";

export default function InterviewProgress({
  state,
}: {
  state: Pick<
    CandidateWorkspace,
    "interview" | "count" | "accepted" | "current"
  >;
}) {
  const { interview, count, accepted, current } = state;
  return (
    <aside className="interview-aside" aria-label="Interview progress">
      <span className="eyebrow">YOUR NEXT CHAPTER</span>
      <h2>
        A little more
        <br />
        about you.
      </h2>
      <p>
        Six questions. Your experience,
        <br className="desktop-break" /> in your own words.
      </p>
      {interview && (
        <>
          <div className="role-label">
            YOUR ROLE<strong>{interview.role}</strong>
          </div>
          <div className="progress-label">
            <span>Interview progress</span>
            <strong>{count} of 6</strong>
          </div>
          <progress
            value={count}
            max={6}
            aria-label={`${count} of 6 answers received`}
          />
          <ol className="question-steps" aria-label="Question steps">
            {interview.questions.map((q) => {
              const done =
                interview.progress.questions.some(
                  (p) => p.question_id === q.id && p.answered,
                ) || accepted?.question.id === q.id;
              return (
                <li
                  key={q.id}
                  className={
                    done
                      ? "done"
                      : q.id === current?.id && !accepted
                        ? "active"
                        : ""
                  }
                  aria-current={
                    q.id === current?.id && !accepted ? "step" : undefined
                  }
                >
                  <span>{done ? "✓" : String(q.number).padStart(2, "0")}</span>
                  <span>Question {q.number}</span>
                  <span className="step-state">
                    {done
                      ? "Received"
                      : q.id === current?.id && !accepted
                        ? "Up next"
                        : ""}
                  </span>
                </li>
              );
            })}
          </ol>
        </>
      )}
      <div className="aside-note">
        <span aria-hidden="true">↳</span>
        <p>
          Your accepted answers are saved.
          <br />
          Return with this same personal link.
        </p>
      </div>
    </aside>
  );
}
