"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";
import TextAnswer from "./text-answer";
import AudioAnswer from "./audio-answer";
export default function AnswerForm({
  state,
}: {
  state: Pick<
    CandidateWorkspace,
    | "submit"
    | "mode"
    | "setMode"
    | "setError"
    | "busy"
    | "refreshing"
    | "text"
    | "file"
    | "error"
    | "fileInput"
    | "setFile"
    | "setText"
  >;
}) {
  const {
    submit,
    mode,
    setMode,
    setError,
    busy,
    refreshing,
    text,
    file,
    error,
  } = state;
  return (
    <form onSubmit={submit} className="answer-form">
      <div className="answer-tabs" role="group" aria-label="Answer format">
        <button
          type="button"
          className={mode === "text" ? "selected" : ""}
          aria-pressed={mode === "text"}
          disabled={busy}
          onClick={() => {
            setMode("text");
            setError(null);
          }}
        >
          <span aria-hidden="true">Aa</span> Write an answer
        </button>
        <button
          type="button"
          className={mode === "audio" ? "selected" : ""}
          aria-pressed={mode === "audio"}
          disabled={busy}
          onClick={() => {
            setMode("audio");
            setError(null);
          }}
        >
          <span aria-hidden="true">≋</span> Upload audio
        </button>
      </div>
      {mode === "text" ? (
        <TextAnswer state={state} />
      ) : (
        <AudioAnswer state={state} />
      )}
      {error && (
        <div role="alert" className="error-notice">
          {error}
          <span>
            Retrying an unchanged answer is safe. Your draft stays here until
            you leave or reload.
          </span>
        </div>
      )}
      <div className="submit-row">
        <p>
          <span aria-hidden="true">↗</span> You’ll get a receipt as soon as
          <br />
          your answer is accepted.
        </p>
        <button
          className="primary-button"
          type="submit"
          disabled={busy || (mode === "text" ? !text.trim() : !file)}
        >
          {busy
            ? refreshing
              ? "Checking progress…"
              : mode === "audio"
                ? "Uploading answer…"
                : "Sending answer…"
            : "Submit answer"}
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </form>
  );
}
