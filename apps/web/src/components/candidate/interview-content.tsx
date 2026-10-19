"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";
import SubmissionReceipt from "./submission-receipt";
import CompletionSummary from "./completion-summary";
import QuestionPanel from "./question-panel";

export default function InterviewContent({
  state,
}: {
  state: CandidateWorkspace;
}) {
  const {
    loading,
    missing,
    blocked,
    interview,
    accepted,
    current,
    error,
    heading,
    busy,
    refresh,
  } = state;
  if (loading)
    return (
      <div className="state-card">
        <span className="loading-dot" />
        <h1 ref={heading} tabIndex={-1}>
          Opening your interview…
        </h1>
        <p>Finding your questions and saved progress.</p>
      </div>
    );
  if (missing)
    return (
      <div className="state-card">
        <span className="eyebrow">PERSONAL LINK REQUIRED</span>
        <h1 ref={heading} tabIndex={-1}>
          Your interview starts with an invitation.
        </h1>
        <p>
          Open the personal link shared by HR. You don’t need an account or
          password.
        </p>
        <p className="muted">
          If you can’t find it, ask your HR contact to resend your link.
        </p>
      </div>
    );
  if (blocked)
    return (
      <div className="state-card">
        <span className="eyebrow">LET’S GET YOU BACK IN</span>
        <h1 ref={heading} tabIndex={-1}>
          This link isn’t available.
        </h1>
        <p role="alert">{error}</p>
        <p className="muted">
          Your previously accepted answers are still saved. Contact HR for help.
        </p>
      </div>
    );
  if (!interview)
    return (
      <div className="state-card">
        <h1 ref={heading} tabIndex={-1}>
          We couldn’t open your interview.
        </h1>
        <p role="alert">{error}</p>
        <button
          className="primary-button"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {busy ? "Trying again…" : "Try again"}
        </button>
      </div>
    );
  if (accepted) return <SubmissionReceipt state={state} />;
  if (interview.progress.complete) return <CompletionSummary state={state} />;
  if (current) return <QuestionPanel state={state} />;
  return (
    <div className="state-card">
      <h1 ref={heading} tabIndex={-1}>
        Let’s refresh your progress.
      </h1>
      <button
        className="primary-button"
        disabled={busy}
        onClick={() => void refresh()}
      >
        Reload interview
      </button>
    </div>
  );
}
