"use client";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import {
  HRApi,
  type Application,
  type Job,
  type Review,
  type Role,
} from "../lib/hr-api";
type Props = {
  api: HRApi;
  enabled: boolean;
  roleId: string;
  applicationId: string;
  offset: number;
  jobOffset: number;
  tab: "candidates" | "jobs";
  reload: number;
  report: (error: unknown) => void;
  setRoleId: Dispatch<SetStateAction<string>>;
};
export function useHRReviewData({
  api,
  enabled,
  roleId,
  applicationId,
  offset,
  jobOffset,
  tab,
  reload,
  report,
  setRoleId,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setRolesLoading(true);
    api
      .roles()
      .then((rows) => {
        if (!cancelled) {
          setRoles(rows);
          setRoleId((current) => current || rows[0]?.id || "");
        }
      })
      .catch((e) => {
        if (!cancelled) report(e);
      })
      .finally(() => {
        if (!cancelled) setRolesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, enabled, report, reload, setRoleId]);
  useEffect(() => {
    if (!enabled || !roleId || tab !== "candidates") return;
    let cancelled = false;
    setCandidatesLoading(true);
    setApplications([]);
    api
      .applications(roleId, offset)
      .then((rows) => {
        if (!cancelled) setApplications(rows);
      })
      .catch((e) => {
        if (!cancelled) report(e);
      })
      .finally(() => {
        if (!cancelled) setCandidatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, enabled, roleId, offset, tab, reload, report]);
  useEffect(() => {
    setReview((current) =>
      current?.application.id === applicationId ? current : null,
    );
    if (!enabled || !applicationId || tab !== "candidates") return;
    let cancelled = false;
    setReviewLoading(true);
    api
      .review(applicationId)
      .then((result) => {
        if (!cancelled) setReview(result);
      })
      .catch((e) => {
        if (!cancelled) report(e);
      })
      .finally(() => {
        if (!cancelled) setReviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, enabled, applicationId, tab, reload, report]);
  useEffect(() => {
    if (!enabled || tab !== "jobs") return;
    let cancelled = false;
    setJobsLoading(true);
    setJobs([]);
    api
      .jobs(jobOffset)
      .then((rows) => {
        if (!cancelled) setJobs(rows);
      })
      .catch((e) => {
        if (!cancelled) report(e);
      })
      .finally(() => {
        if (!cancelled) setJobsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, enabled, tab, jobOffset, reload, report]);

  return {
    roles: enabled ? roles : [],
    applications: enabled ? applications : [],
    review: enabled ? review : null,
    jobs: enabled ? jobs : [],
    loading:
      enabled &&
      (rolesLoading ||
        (tab === "candidates"
          ? (!!roleId && candidatesLoading) ||
            (!!applicationId && reviewLoading)
          : jobsLoading)),
  };
}
