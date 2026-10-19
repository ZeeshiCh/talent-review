import Link from "next/link";
export default function Brand() {
  return (
    <Link className="wordmark" href="/" aria-label="Talent Review home">
      <span className="brand-mark" aria-hidden="true">
        t.
      </span>
      talent<span className="wordmark-light">review</span>
    </Link>
  );
}
