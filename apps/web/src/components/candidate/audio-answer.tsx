"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";

export default function AudioAnswer({
  state,
}: {
  state: Pick<
    CandidateWorkspace,
    "file" | "fileInput" | "busy" | "setFile" | "setError"
  >;
}) {
  const { file, fileInput, busy, setFile, setError } = state;
  return (
    <div className="audio-answer">
      <label htmlFor="answer-audio" className="upload-label">
        <span className="upload-icon" aria-hidden="true">
          ↑
        </span>
        <strong>{file ? file.name : "Choose your audio answer"}</strong>
        <span>
          {file
            ? `${(file.size / (1024 * 1024)).toFixed(2)} MiB · Ready to submit`
            : "M4A, MP3, or WAV · Up to 20 MiB"}
        </span>
        <span className="choose-file">
          {file ? "Choose a different file" : "Browse files"}
        </span>
      </label>
      <input
        ref={fileInput}
        id="answer-audio"
        className="sr-only"
        type="file"
        accept=".m4a,.mp3,.wav,audio/mp4,audio/mpeg,audio/wav"
        disabled={busy}
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null);
          setError(null);
        }}
        aria-describedby="audio-hint"
      />
      <p id="audio-hint" className="audio-note">
        Your recording is stored for HR to review. Audio transcription isn’t
        available.
      </p>
    </div>
  );
}
