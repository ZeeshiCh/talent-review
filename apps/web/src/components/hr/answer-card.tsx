"use client";
import { FormEvent, useRef, useState } from "react";
import { Answer, HRApi } from "../../lib/hr-api";
import StatusBadge from "./status-badge";
import PrivateAudio from "./private-audio";
import ScoreSummary from "./score-summary";
import ReviewHistory from "./review-history";
import OverrideForm from "./override-form";
export default function AnswerCard({
  answer,
  api,
  refresh,
  onError,
}: {
  answer: Answer;
  api: HRApi;
  refresh: () => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const [score, setScore] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const lock = useRef(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setMessage("");
    try {
      await api.override(answer.id, Number(score), reason.trim());
      setReason("");
      setScore("");
      setMessage("Override saved.");
      await refresh();
    } catch (e) {
      onError(e);
      setMessage(
        "Could not confirm this override. Refresh review before submitting again.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function retry() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.retry(answer.job!.id);
      setMessage(
        result.requeued ? "Job queued for retry." : "Job is already queued.",
      );
      await refresh();
    } catch (e) {
      onError(e);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <article className={`hr-answer ${answer.is_current ? "" : "hr-history"}`}>
      <div className="hr-row">
        <strong>
          {answer.is_current ? "Current answer" : "Earlier revision"}{" "}
          {answer.source_id && (
            <span className="muted">· {answer.source_id}</span>
          )}
        </strong>
        <StatusBadge status={answer.job?.status || "No job"} />
      </div>
      <p className="hr-meta">
        {answer.input_kind === "text"
          ? "Written answer"
          : answer.input_kind === "audio"
            ? "Audio answer"
            : "Missing content"}{" "}
        · Received {new Date(answer.submitted_at).toLocaleString()}
      </p>
      {answer.source_submitted_at && (
        <p className="hr-meta">
          Source submission: {answer.source_submitted_at}
        </p>
      )}
      {answer.text && <div className="hr-answer-text">{answer.text}</div>}
      {answer.input_kind === "audio" && (
        <PrivateAudio api={api} id={answer.id} onError={onError} />
      )}
      {answer.input_kind === "missing" && (
        <p className="muted">
          No answer content was supplied. Human review is required.
        </p>
      )}
      <ScoreSummary answer={answer} />
      {answer.job?.review_reason && (
        <p className="hr-notice">Needs a person: {answer.job.review_reason}</p>
      )}
      {answer.job?.status === "failed" && (
        <div className="hr-notice failure">
          <strong>Scoring failed</strong>
          <p>
            {answer.job.error_message} ({answer.job.error_code})
          </p>
          {answer.job.retryable && (
            <p>
              Automatic retry scheduled:{" "}
              {answer.job.retry_at
                ? new Date(answer.job.retry_at).toLocaleString()
                : "pending"}
            </p>
          )}
          <button disabled={busy} className="hr-secondary" onClick={retry}>
            Retry scoring job
          </button>
        </div>
      )}
      <ReviewHistory overrides={answer.overrides} />
      {answer.is_current ? (
        <OverrideForm
          score={score}
          reason={reason}
          busy={busy}
          onScore={setScore}
          onReason={setReason}
          onSubmit={save}
        />
      ) : (
        <p className="hr-meta">
          This revision is preserved for reference. Review the current answer
          above.
        </p>
      )}
      {message && (
        <p role="status" className="hr-notice">
          {message}
        </p>
      )}
    </article>
  );
}
