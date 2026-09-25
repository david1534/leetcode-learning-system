import { useEffect, useRef, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import type { CoachMessage, Evaluation, Finding, Session } from "./types";

export interface CompletionValues {
  rating: string;
  takeaway: string;
  explained: boolean;
  constraints: boolean;
  minutes: number | null;
  findings: Finding[];
  publish: boolean;
  recallConfirmed: boolean;
}
interface Props {
  session: Session;
  facts: Evaluation;
  review: CoachMessage | undefined;
  elapsed: number;
  unpublishedCount: number;
  busy: boolean;
  takeaway: string;
  setTakeaway: (value: string) => void;
  cancel: () => void;
  onFinish: (values: CompletionValues) => void;
}

export function Dialog({
  children,
  cancel,
  titleId = "finish-title",
  closeLabel = "Cancel completion",
}: {
  children: React.ReactNode;
  cancel: () => void;
  titleId?: string;
  closeLabel?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        cancel();
      }}
    >
      <button
        className="icon-button dialog-close"
        aria-label={closeLabel}
        onClick={cancel}
      >
        <X />
      </button>
      {children}
    </dialog>
  );
}

export default function CompletionDialog({
  session,
  facts,
  review,
  elapsed,
  unpublishedCount,
  busy,
  takeaway,
  setTakeaway,
  cancel,
  onFinish,
}: Props) {
  const [rating, setRating] = useState(facts.recommended_rating);
  const [explained, setExplained] = useState(false);
  const [constraints, setConstraints] = useState(false);
  const [actualMinutes, setActualMinutes] = useState("");
  const [finishFindings, setFinishFindings] = useState<Finding[]>(
    facts.evidence || [],
  );
  useEffect(() => {
    if (review?.findings) {
      setFinishFindings(review.findings);
      setExplained(
        review.findings.some(
          (f) => f.dimension === "explanation" && f.value === "success",
        ),
      );
      setConstraints(
        review.findings.some(
          (f) => f.dimension === "constraints" && f.value === "success",
        ),
      );
    }
  }, [review?.request_id]);
  const submit = (publish: boolean) =>
    onFinish({
      rating,
      takeaway,
      explained,
      constraints,
      minutes: actualMinutes ? Number(actualMinutes) : null,
      findings: finishFindings,
      publish,
      recallConfirmed: rating !== "unknown" && !!session.initial_reasoning,
    });
  return (
    <Dialog cancel={cancel}>
      <span className="eyebrow">Save this practice</span>
      <h2 id="finish-title">What will you remember next time?</h2>
      <p>What would you recognize or do differently next time?</p>
      <label htmlFor="takeaway">A short takeaway (optional)</label>
      <textarea
        id="takeaway"
        rows={3}
        value={takeaway}
        onChange={(e) => setTakeaway(e.target.value)}
        placeholder="Next time, I’ll notice…"
      />
      <div className="completion-preview">
        <strong>
          {session.assessment_before_help
            ? "Independent assessment ended for help. Guided work is recorded separately."
            : facts.tests_passed
              ? "Your saved code passed its checks."
              : session.activity === "recall"
                ? "Short retrieval; implementation scheduling stays separate."
                : "An unfinished attempt is useful evidence. Your code will be preserved."}
        </strong>
        <p>
          Help: {facts.assistance_level}. Active time:{" "}
          {Math.round(elapsed / 60)} minutes.
        </p>
      </div>
      {review?.findings && (
        <section>
          <h3>Drafted from your evidence</h3>
          {review.findings
            .filter((f) => f.dimension !== "misconception")
            .map((f, i) => (
              <p key={i}>
                <strong>{f.dimension}:</strong>{" "}
                {f.value === "unknown"
                  ? "not established"
                  : f.value === "success"
                    ? "supported by recorded evidence"
                    : "needs review"}
                <small> · Coach judgment</small>
              </p>
            ))}
        </section>
      )}
      <label className="checkbox">
        <input
          type="checkbox"
          checked={explained}
          onChange={(e) => setExplained(e.target.checked)}
        />
        Explanation of why the approach works is recorded
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={constraints}
          onChange={(e) => setConstraints(e.target.checked)}
        />
        Time and space requirements were checked
      </label>
      <section>
        <label>
          Recall rating
          <select value={rating} onChange={(e) => setRating(e.target.value)}>
            {facts.recall_outcome === "unknown" && (
              <option value="unknown">Unknown · scheduling unchanged</option>
            )}
            <option value="again">Again · specified recall was missing</option>
            {facts.recall_outcome !== "failure" &&
              session.initial_reasoning && (
                <>
                  <option value="hard">
                    Hard · recalled with substantial effort
                  </option>
                  <option value="good">Good · ordinary effort</option>
                  <option value="easy">Easy · fluent recall</option>
                </>
              )}
          </select>
        </label>
        <p className="muted">{facts.rating_rationale}</p>
        <label>
          Total active minutes
          <input
            type="number"
            min="0.1"
            max="1440"
            step="0.1"
            value={actualMinutes}
            onChange={(e) => setActualMinutes(e.target.value)}
            placeholder={`${Math.round(elapsed / 60)} · calculated`}
          />
        </label>
        {finishFindings.map((f, i) => (
          <div className="finding" key={i}>
            <label>
              {f.dimension}
              <select
                value={f.value}
                onChange={(e) =>
                  setFinishFindings(
                    finishFindings.map((v, j) =>
                      j === i
                        ? {
                            ...v,
                            value: e.target.value as Finding["value"],
                            source: "learner_amendment",
                          }
                        : v,
                    ),
                  )
                }
              >
                <option value="success">Supported</option>
                <option value="failure">Not yet supported</option>
                <option value="unknown">Unknown / disputed</option>
              </select>
            </label>
            {f.evidence && <blockquote>{f.evidence}</blockquote>}
          </div>
        ))}
      </section>
      <p className="muted">
        Publication includes your code, reviewed learning evidence, and brief
        takeaway. Full coach conversations stay private.{" "}
        {unpublishedCount > 0
          ? `Also includes ${unpublishedCount} earlier saved item(s).`
          : ""}
      </p>
      <p className="muted">
        Destination: github.com/david1534/leetcode-learning-system
      </p>
      <div className="button-row">
        <button
          className="primary"
          disabled={busy}
          onClick={() => submit(false)}
        >
          Finish locally
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => submit(true)}
        >
          Publish & finish
          <ArrowRight size={16} />
        </button>
      </div>
    </Dialog>
  );
}
