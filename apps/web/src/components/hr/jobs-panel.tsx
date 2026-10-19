"use client";
import { HRWorkspaceState } from "../../hooks/use-hr-workspace";
import StatusBadge from "./status-badge";
export default function JobsPanel({
  state,
}: {
  state: Pick<
    HRWorkspaceState,
    "jobs" | "loading" | "busy" | "retryJob" | "jobOffset" | "changeJobPage"
  >;
}) {
  const { jobs, loading, busy, retryJob, jobOffset, changeJobPage } = state;
  return (
    <section className="hr-jobs">
      <div className="hr-row">
        <h2>Scoring jobs</h2>
        <span className="hr-meta">
          Refresh to see the latest worker results.
        </span>
      </div>
      {loading && <p role="status">Loading jobs…</p>}
      {!loading && jobs.length === 0 && <p>No jobs on this page.</p>}
      {jobs.map((job) => (
        <article className="hr-job" key={job.id}>
          <div className="hr-row">
            <StatusBadge status={job.status} />
            <span className="hr-meta">
              Attempts {job.attempts} / {job.max_attempts}
            </span>
          </div>
          <p className="hr-meta">
            Answer <code>{job.answer_id}</code>
          </p>
          {job.error_message && (
            <p>
              {job.error_message} ({job.error_code})
            </p>
          )}
          {job.review_reason && <p>{job.review_reason}</p>}
          {job.retryable && (
            <p className="hr-meta">
              Automatic retry:{" "}
              {job.retry_at
                ? new Date(job.retry_at).toLocaleString()
                : "pending"}
            </p>
          )}
          {job.status === "failed" && (
            <button
              className="hr-secondary"
              disabled={busy}
              onClick={() => void retryJob(job.id)}
            >
              Retry scoring job
            </button>
          )}
        </article>
      ))}
      <div className="hr-pagination">
        <button
          className="hr-secondary"
          disabled={!jobOffset || loading}
          onClick={() => changeJobPage(Math.max(0, jobOffset - 50))}
        >
          Previous jobs
        </button>
        <button
          className="hr-secondary"
          disabled={jobs.length < 50 || loading}
          onClick={() => changeJobPage(jobOffset + 50)}
        >
          Next jobs
        </button>
      </div>
    </section>
  );
}
