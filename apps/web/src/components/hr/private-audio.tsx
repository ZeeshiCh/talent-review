"use client";
import { useEffect, useRef, useState } from "react";
import { HRApi } from "../../lib/hr-api";
export default function PrivateAudio({
  api,
  id,
  onError,
}: {
  api: HRApi;
  id: string;
  onError: (error: unknown) => void;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef(true);
  const objectURL = useRef("");
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      if (objectURL.current) URL.revokeObjectURL(objectURL.current);
    };
  }, []);
  async function load() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const blob = await api.audio(id);
      if (active.current) {
        const value = URL.createObjectURL(blob);
        objectURL.current = value;
        setUrl(value);
      }
    } catch (e) {
      if (active.current) {
        setError("Audio could not be loaded. Try again.");
        onError(e);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  return (
    <div className="hr-audio">
      {url ? (
        <audio
          controls
          preload="metadata"
          src={url}
          aria-label="Audio answer"
        />
      ) : (
        <button className="hr-secondary" disabled={busy} onClick={load}>
          {busy ? "Loading audio…" : "Load private audio"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
