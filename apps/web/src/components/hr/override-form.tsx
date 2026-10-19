"use client";
import { FormEvent } from "react";
import SelectField from "../ui/select-field";
type Props = {
  score: string;
  reason: string;
  busy: boolean;
  onScore: (value: string) => void;
  onReason: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
};
export default function OverrideForm({
  score,
  reason,
  busy,
  onScore,
  onReason,
  onSubmit,
}: Props) {
  return (
    <form onSubmit={onSubmit} className="hr-override">
      <h4>Set an HR score</h4>
      <p className="hr-meta">
        Your reason is saved in the audit history. The original suggestion stays
        available.
      </p>
      <div className="hr-fields">
        <label>
          Score
          <SelectField
            aria-label="Score"
            required
            value={score}
            onValueChange={onScore}
            disabled={busy}
            placeholder="Choose score"
            options={[1, 2, 3, 4].map((value) => ({
              value: String(value),
              label: `${value} / 4`,
            }))}
          />
        </label>
        <label>
          Reason
          <textarea
            required
            maxLength={2000}
            value={reason}
            onChange={(event) => onReason(event.target.value)}
            disabled={busy}
            placeholder="Explain your judgment against the grading guide"
          />
        </label>
      </div>
      <button
        className="primary-button"
        disabled={busy || !score || !reason.trim()}
      >
        {busy ? "Saving…" : "Save HR override"}
      </button>
    </form>
  );
}
