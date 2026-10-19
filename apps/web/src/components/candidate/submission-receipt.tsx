"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";
import Check from "./check-icon";
export default function SubmissionReceipt({
  state,
}: {
  state: Pick<
    CandidateWorkspace,
    "accepted" | "complete" | "heading" | "error" | "busy" | "refresh"
  >;
}) {
  const { accepted, complete, heading, error, busy, refresh } = state;
  if (!accepted) return null;
  return (
    <div className="state-card receipt-card" aria-live="polite">
      <Check large />
      <span className="eyebrow">
        QUESTION {accepted.question.number} · RECEIVED
      </span>
      <h1 ref={heading} tabIndex={-1}>
        {complete ? "Your interview is complete." : "Your answer is in."}
      </h1>
      <p>
        {complete
          ? "All six answers have arrived safely. Thank you for sharing your experience."
          : "Your answer has arrived safely. You can move on whenever you’re ready."}
      </p>
      <div className="receipt-details">
        <span>
          {accepted.receipt.input_kind === "audio"
            ? "Audio file"
            : "Written answer"}{" "}
          received
        </span>
        <code>Receipt {accepted.receipt.receipt}</code>
        <span>{new Date(accepted.receipt.submitted_at).toLocaleString()}</span>
      </div>
      {error && (
        <p role="alert" className="error-notice">
          Your answer is saved. {error}
        </p>
      )}
      <button
        className="primary-button"
        disabled={busy}
        onClick={() => void refresh(true)}
      >
        {busy
          ? "Loading saved progress…"
          : complete
            ? "View confirmation"
            : "Continue to next question"}
        <span aria-hidden="true">→</span>
      </button>
      <p className="muted small">
        {complete
          ? "HR will review your answers and follow up with you."
          : "No need to submit this answer again."}
      </p>
    </div>
  );
}
