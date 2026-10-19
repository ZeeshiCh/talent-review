"use client";
import type { CandidateWorkspace } from "../../hooks/use-candidate-interview";

export default function TextAnswer({
  state,
}: {
  state: Pick<CandidateWorkspace, "text" | "setText" | "busy">;
}) {
  const { text, setText, busy } = state;
  return (
    <div className="text-answer">
      <label htmlFor="answer-text">Your answer</label>
      <textarea
        id="answer-text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={50000}
        rows={9}
        disabled={busy}
        placeholder="Start wherever feels natural. What happened, what did you do, and what changed?"
        aria-describedby="answer-hint"
      />
      <div className="input-footer" id="answer-hint">
        <span>Be specific. Be yourself.</span>
        <span>{text.length.toLocaleString()} / 50,000</span>
      </div>
    </div>
  );
}
