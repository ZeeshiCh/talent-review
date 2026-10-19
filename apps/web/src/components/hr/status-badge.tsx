"use client";

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`hr-badge ${status === "failed" ? "failed" : status === "scored" ? "scored" : ""}`}
    >
      {status}
    </span>
  );
}
