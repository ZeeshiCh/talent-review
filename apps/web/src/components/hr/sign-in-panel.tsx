"use client";
import { HRWorkspaceState } from "../../hooks/use-hr-workspace";
export default function SignInPanel({
  state,
}: {
  state: Pick<
    HRWorkspaceState,
    | "email"
    | "setEmail"
    | "password"
    | "setPassword"
    | "busy"
    | "error"
    | "signIn"
  >;
}) {
  const { email, setEmail, password, setPassword, busy, error, signIn } = state;
  return (
    <main className="hr-login">
      <span className="eyebrow">A THOUGHTFUL REVIEW STARTS HERE</span>
      <h1>Welcome back.</h1>
      <p>Sign in to review candidate answers and make your own judgment.</p>
      <div className="hr-notice">
        Demo sign-in · Use the HR credentials configured for this local
        workspace.
      </div>
      <form onSubmit={signIn}>
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
        </label>
        {error && (
          <p role="alert" className="hr-notice failure">
            {error}
          </p>
        )}
        <button className="primary-button" disabled={busy}>
          {busy ? "Signing in…" : "Sign in to HR workspace"}
        </button>
      </form>
      <p className="hr-meta">For privacy, reloading this page signs you out.</p>
    </main>
  );
}
