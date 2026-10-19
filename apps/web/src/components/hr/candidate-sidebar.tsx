"use client";
import { HRWorkspaceState } from "../../hooks/use-hr-workspace";
import SelectField from "../ui/select-field";
export default function CandidateSidebar({
  state,
}: {
  state: Pick<
    HRWorkspaceState,
    | "roleId"
    | "roles"
    | "applications"
    | "applicationId"
    | "offset"
    | "loading"
    | "selectRole"
    | "selectApplication"
    | "changePage"
  >;
}) {
  const {
    roleId,
    roles,
    applications,
    applicationId,
    offset,
    loading,
    selectRole,
    selectApplication,
    changePage,
  } = state;
  return (
    <aside className="hr-sidebar">
      <label>
        Role
        <SelectField
          aria-label="Role"
          value={roleId}
          onValueChange={selectRole}
          options={roles.map((role) => ({ value: role.id, label: role.name }))}
          placeholder="Select a role"
        />
      </label>
      <h2>
        Candidates{" "}
        <span className="muted">
          {applications.length ? offset + 1 : 0}–{offset + applications.length}
        </span>
      </h2>
      {!loading && applications.length === 0 && (
        <p className="muted">No candidates on this page.</p>
      )}
      <div className="hr-candidate-list">
        {applications.map((item) => (
          <button
            key={item.id}
            aria-pressed={applicationId === item.id}
            onClick={() => selectApplication(item.id)}
          >
            <strong>{item.candidate.name}</strong>
            <span>{item.candidate.email}</span>
            <small>
              {item.answered_count} / {item.total_questions} answers ·{" "}
              {item.complete ? "Complete" : "In progress"}
            </small>
          </button>
        ))}
      </div>
      <div className="hr-pagination">
        <button
          className="hr-secondary"
          disabled={offset === 0 || loading}
          onClick={() => changePage(Math.max(0, offset - 50))}
        >
          Previous
        </button>
        <button
          className="hr-secondary"
          disabled={applications.length < 50 || loading}
          onClick={() => changePage(offset + 50)}
        >
          Next
        </button>
      </div>
    </aside>
  );
}
