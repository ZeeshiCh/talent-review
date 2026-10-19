import Link from "next/link";
import SiteHeader from "../components/ui/site-header";

export default function Home() {
  return (
    <>
      <SiteHeader>
        <Link className="private-label" href="/hr">
          HR sign in →
        </Link>
      </SiteHeader>
      <main className="landing">
        <span className="eyebrow">ROOM FOR YOUR STORY</span>
        <h1>Good conversations start with your experience.</h1>
        <p>
          Talent Review gives you a simple, private space to share your
          interview answers. Write your response or upload an audio recording,
          one question at a time.
        </p>
        <p>
          To begin or return to your interview, open the personal link shared by
          HR. No account or password needed.
        </p>
        <Link className="primary-button" href="/interview">
          About your invitation <span aria-hidden="true">→</span>
        </Link>
        <div className="landing-notes">
          <span>Six thoughtful questions</span>
          <span>Instant submission receipts</span>
          <span>Saved progress</span>
        </div>
      </main>
    </>
  );
}
