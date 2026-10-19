import "./interview.css";
import type { Metadata } from "next";
import InterviewExperience from "./interview-experience";

export const metadata: Metadata = {
  title: "Your interview · Talent Review",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export default function InterviewPage() {
  return <InterviewExperience />;
}
