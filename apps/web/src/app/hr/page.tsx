import type { Metadata } from "next";
import "./hr.css";
import HRWorkspace from "./workspace";
export const metadata: Metadata = {
  title: "HR workspace · Talent Review",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};
export default function HRPage() {
  return <HRWorkspace />;
}
