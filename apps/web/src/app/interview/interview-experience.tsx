"use client";
import { useCandidateInterview } from "../../hooks/use-candidate-interview";
import InterviewProgress from "../../components/candidate/interview-progress";
import InterviewContent from "../../components/candidate/interview-content";
import SiteHeader from "../../components/ui/site-header";
import SiteFooter from "../../components/ui/site-footer";
export default function InterviewExperience() {
  const state = useCandidateInterview();
  return (
    <div className="candidate-shell">
      <SiteHeader>
        <span className="private-label">
          <span aria-hidden="true">◈</span> Private interview
        </span>
      </SiteHeader>
      <main className="interview-layout" id="main-content">
        <InterviewProgress state={state} />
        <section
          className="interview-workspace"
          aria-busy={state.busy || state.loading}
        >
          <InterviewContent state={state} />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
