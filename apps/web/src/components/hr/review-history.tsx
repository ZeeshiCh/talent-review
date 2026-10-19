"use client";
import { Answer } from "../../lib/hr-api";
export default function ReviewHistory({
  overrides,
}: {
  overrides: Answer["overrides"];
}) {
  return (
    <details className="hr-audit">
      <summary>Review history ({overrides.length})</summary>
      {overrides.length === 0 ? (
        <p>No HR overrides yet.</p>
      ) : (
        overrides.map((item) => (
          <div key={item.id}>
            <strong>{item.score} / 4</strong> ·{" "}
            {new Date(item.created_at).toLocaleString()}
            <p>{item.reason}</p>
            <small>Reviewer {item.actor_id}</small>
          </div>
        ))
      )}
    </details>
  );
}
