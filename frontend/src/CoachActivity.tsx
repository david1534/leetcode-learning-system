import { useEffect, useState } from "react";

export default function CoachActivity({
  phase,
}: {
  phase: "sending" | "reply";
}) {
  const [waiting, setWaiting] = useState(false);
  useEffect(() => {
    setWaiting(false);
    const timer = setTimeout(() => setWaiting(true), 12000);
    return () => clearTimeout(timer);
  }, [phase]);

  return (
    <div className="coach-activity" role="status" aria-atomic="true">
      <span className="coach-activity-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <div>
        <p className="coach-activity-label">
          {phase === "sending"
            ? waiting
              ? "Still sending your question…"
              : "Sending question…"
            : waiting
              ? "Still preparing your reply…"
              : "Preparing a reply…"}
        </p>
        <p className="coach-activity-hint">
          You can keep coding while you wait.
        </p>
      </div>
    </div>
  );
}
