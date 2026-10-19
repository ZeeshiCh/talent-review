"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ApiError,
  CandidateApi,
  MAX_AUDIO_BYTES,
  SubmissionKeys,
  personalToken,
  type Interview,
  type Question,
  type Receipt,
  type Submission,
} from "../lib/candidate-api";

type Accepted = { receipt: Receipt; question: Question };
const messageOf = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";

export function useCandidateInterview() {
  const [token, setToken] = useState<string | null>(null);
  const [interview, setInterview] = useState<Interview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [missing, setMissing] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"text" | "audio">("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [accepted, setAccepted] = useState<Accepted | null>(null);
  const keys = useRef(new SubmissionKeys());
  const linkToken = useRef<string | null | undefined>(undefined);
  const inFlight = useRef(false);
  const activeRequest = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const current = interview?.questions.find(
    (q) => q.id === interview.progress.next_question_id,
  );

  useEffect(() => {
    function readLink() {
      const next = personalToken(window.location.hash);
      if (next === linkToken.current) return;
      activeRequest.current?.abort();
      linkToken.current = next;
      setToken(next);
      setMissing(!next);
      setLoading(Boolean(next));
      setInterview(null);
      setAccepted(null);
      setError(null);
      setBlocked(false);
      setText("");
      setFile(null);
      keys.current.clear();
      inFlight.current = false;
      setBusy(false);
      setRefreshing(false);
    }
    readLink();
    window.addEventListener("hashchange", readLink);
    return () => {
      window.removeEventListener("hashchange", readLink);
      activeRequest.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    const api = new CandidateApi(token);
    api
      .interview(controller.signal)
      .then(setInterview)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(messageOf(cause));
        setBlocked(
          cause instanceof ApiError && [401, 403].includes(cause.status),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token]);

  useEffect(() => {
    setText("");
    setFile(null);
    setMode("text");
    keys.current.clear();
    if (fileInput.current) fileInput.current.value = "";
    heading.current?.focus();
  }, [current?.id]);

  const refresh = useCallback(
    async (continueInterview = false) => {
      if (!token || inFlight.current) return;
      inFlight.current = true;
      setBusy(true);
      setRefreshing(true);
      setError(null);
      const controller = new AbortController();
      activeRequest.current = controller;
      try {
        const data = await new CandidateApi(token).interview(controller.signal);
        setInterview(data);
        setLoading(false);
        setBlocked(false);
        if (continueInterview) setAccepted(null);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(messageOf(cause));
        setBlocked(
          cause instanceof ApiError && [401, 403].includes(cause.status),
        );
      } finally {
        if (!controller.signal.aborted) {
          setBusy(false);
          setRefreshing(false);
          setLoading(false);
          inFlight.current = false;
        }
      }
    },
    [token],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !current || inFlight.current) return;
    setError(null);
    if (mode === "text" && (!text.trim() || text.length > 50000)) {
      setError("Write an answer before submitting.");
      return;
    }
    if (mode === "audio" && !file) {
      setError("Choose an audio file before submitting.");
      return;
    }
    if (
      mode === "audio" &&
      file &&
      (file.size === 0 || file.size > MAX_AUDIO_BYTES)
    ) {
      setError("Choose a nonempty audio file smaller than 20 MiB.");
      return;
    }
    let submission: Submission;
    if (mode === "text")
      submission = { questionId: current.id, kind: "text", text };
    else {
      if (!file) return;
      submission = { questionId: current.id, kind: "audio", file };
    }
    const key = keys.current.for(submission);
    const controller = new AbortController();
    activeRequest.current = controller;
    const api = new CandidateApi(token);
    inFlight.current = true;
    setBusy(true);
    try {
      const receipt = await api.submit(submission, key, controller.signal);
      if (receipt.question_id !== current.id || receipt.input_kind !== mode)
        throw new ApiError(
          502,
          "The receipt did not match your answer. Check saved progress.",
        );
      setAccepted({ receipt, question: current }); // Show committed receipt immediately; no waiting for another request.
      setText("");
      setFile(null);
      keys.current.clear();
      heading.current?.focus();
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(messageOf(cause));
      setBlocked(
        cause instanceof ApiError && [401, 403].includes(cause.status),
      );
      if (cause instanceof ApiError && [404, 409].includes(cause.status)) {
        try {
          setInterview(await api.interview(controller.signal));
          setError(
            "Your saved progress has been refreshed. Any previously accepted answer is unchanged.",
          );
        } catch {
          /* Keep the original error and draft if progress cannot be loaded. */
        }
      }
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false);
        inFlight.current = false;
      }
    }
  }

  useEffect(() => {
    heading.current?.focus();
  }, [accepted, loading, blocked]);

  const count = interview
    ? Math.min(
        6,
        interview.progress.answered_count +
          (accepted &&
          !interview.progress.questions.some(
            (q) => q.receipt?.receipt === accepted.receipt.receipt,
          )
            ? 1
            : 0),
      )
    : 0;
  const complete = interview?.progress.complete || (accepted && count === 6);

  return {
    interview,
    loading,
    busy,
    refreshing,
    missing,
    blocked,
    error,
    mode,
    text,
    file,
    accepted,
    current,
    count,
    complete,
    heading,
    fileInput,
    refresh,
    submit,
    setMode,
    setError,
    setText,
    setFile,
  };
}
export type CandidateWorkspace = ReturnType<typeof useCandidateInterview>;
