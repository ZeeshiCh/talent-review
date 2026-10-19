export default function Check({ large = false }: { large?: boolean }) {
  return (
    <span
      className={large ? "check-icon large" : "check-icon"}
      aria-hidden="true"
    >
      ✓
    </span>
  );
}
