"use client";
import SiteHeader from "../ui/site-header";
import { HRWorkspaceState } from "../../hooks/use-hr-workspace";
export default function WorkspaceHeader({
  state,
}: {
  state: Pick<HRWorkspaceState, "session" | "busy" | "signOut">;
}) {
  const { session, busy, signOut } = state;
  return (
    <SiteHeader>
      <div className="hr-row">
        <span className="private-label">HR workspace · Demo sign-in</span>
        {session && (
          <button className="hr-secondary" disabled={busy} onClick={signOut}>
            Sign out
          </button>
        )}
      </div>
    </SiteHeader>
  );
}
