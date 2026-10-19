"use client";
import { useHRWorkspace } from "../../hooks/use-hr-workspace";
import WorkspaceHeader from "../../components/hr/workspace-header";
import SignInPanel from "../../components/hr/sign-in-panel";
import CandidateSidebar from "../../components/hr/candidate-sidebar";
import CandidateReview from "../../components/hr/candidate-review";
import JobsPanel from "../../components/hr/jobs-panel";

export default function HRWorkspace() {
  const state = useHRWorkspace();
  return (
    <>
      <WorkspaceHeader state={state} />
      {!state.session ? (
        <SignInPanel state={state} />
      ) : (
        <main className="hr-shell">
          <div className="hr-title">
            <div>
              <span className="eyebrow">PEOPLE, BEFORE NUMBERS</span>
              <h1>Review workspace</h1>
              <p className="muted">
                Hello, {state.session.user.name}. Suggestions support your
                judgment. You make the decision.
              </p>
            </div>
            <button
              className="hr-secondary"
              disabled={state.loading}
              onClick={() => {
                state.clearError();
                void state.refresh();
              }}
            >
              Refresh data
            </button>
          </div>
          <nav className="hr-tabs" aria-label="HR sections">
            <button
              aria-current={state.tab === "candidates" ? "page" : undefined}
              onClick={() => state.changeTab("candidates")}
            >
              Candidate reviews
            </button>
            <button
              aria-current={state.tab === "jobs" ? "page" : undefined}
              onClick={() => state.changeTab("jobs")}
            >
              Scoring jobs
            </button>
          </nav>
          {state.error && (
            <div role="alert" className="hr-notice failure">
              {state.error}
            </div>
          )}
          {state.tab === "candidates" ? (
            <div className="hr-layout">
              <CandidateSidebar state={state} />
              <CandidateReview state={state} />
            </div>
          ) : (
            <JobsPanel state={state} />
          )}
        </main>
      )}
    </>
  );
}
