"use client";
import { useHRReviewData } from "./use-hr-review-data";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { HRApi, HRError, HRSession } from "../lib/hr-api";
export function useHRWorkspace() {
  const [session, setSession] = useState<HRSession | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [roleId, setRoleId] = useState("");
  const [offset, setOffset] = useState(0);
  const [applicationId, setApplicationId] = useState("");
  const [jobOffset, setJobOffset] = useState(0);
  const [tab, setTab] = useState<"candidates" | "jobs">("candidates");
  const [reload, setReload] = useState(0);
  const action = useRef(false);
  const [api, setApi] = useState(() => new HRApi());
  const report = useCallback((e: unknown) => {
    if (e instanceof HRError && e.status === 401) {
      setSession(null);
      setApi(new HRApi());
      setPassword("");
      setError("Your session ended. Sign in again.");
    } else
      setError(
        e instanceof Error ? e.message : "Something went wrong. Try again.",
      );
  }, []);
  const { roles, applications, review, jobs, loading } = useHRReviewData({
    api,
    enabled: !!session,
    roleId,
    applicationId,
    offset,
    jobOffset,
    tab,
    reload,
    report,
    setRoleId,
  });
  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (action.current) return;
    action.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await new HRApi().login(email, password);
      setPassword("");
      setApi(new HRApi(result.token));
      setSession(result);
      setRoleId("");
      setApplicationId("");
      setOffset(0);
      setJobOffset(0);
    } catch (e) {
      setPassword("");
      if (e instanceof HRError && e.status === 401)
        setError("Invalid email or password. Please try again.");
      else report(e);
    } finally {
      action.current = false;
      setBusy(false);
    }
  }
  async function signOut() {
    if (action.current) return;
    action.current = true;
    setBusy(true);
    try {
      await api.logout();
      setSession(null);
      setApi(new HRApi());
      setError("");
    } catch (e) {
      report(e);
    } finally {
      action.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!session) return;
    const duration = new Date(session.expires_at).getTime() - Date.now();
    const timer = setTimeout(
      () => report(new HRError(401, "Expired")),
      Math.max(0, duration),
    );
    return () => clearTimeout(timer);
  }, [session, report]);
  async function refresh() {
    setReload((value) => value + 1);
  }
  async function retryJob(id: string) {
    if (action.current) return;
    action.current = true;
    setBusy(true);
    setError("");
    try {
      await api.retry(id);
      await refresh();
    } catch (e) {
      report(e);
    } finally {
      action.current = false;
      setBusy(false);
    }
  }
  function selectRole(id: string) {
    setRoleId(id);
    setApplicationId("");
    setOffset(0);
    setError("");
  }
  function selectApplication(id: string) {
    setApplicationId(id);
    setError("");
  }
  function changePage(next: number) {
    setOffset(next);
    setApplicationId("");
  }
  function changeJobPage(next: number) {
    setJobOffset(next);
  }
  function changeTab(next: "candidates" | "jobs") {
    setTab(next);
    setError("");
  }
  function clearError() {
    setError("");
  }
  return {
    api,
    session,
    email,
    setEmail,
    password,
    setPassword,
    error,
    busy,
    roles,
    roleId,
    applications,
    offset,
    applicationId,
    review,
    jobs,
    jobOffset,
    tab,
    loading,
    signIn,
    signOut,
    refresh,
    retryJob,
    report,
    selectRole,
    selectApplication,
    changePage,
    changeJobPage,
    changeTab,
    clearError,
  };
}
export type HRWorkspaceState = ReturnType<typeof useHRWorkspace>;
