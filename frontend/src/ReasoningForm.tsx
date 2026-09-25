import { ArrowRight, Lightbulb } from "lucide-react";

interface Props {
  answer: string;
  quality: string;
  busy: boolean;
  setAnswer: (value: string) => void;
  setQuality: (value: string) => void;
  submit: () => void;
}

export default function ReasoningForm({
  answer,
  quality,
  busy,
  setAnswer,
  setQuality,
  submit,
}: Props) {
  return (
    <div className="panel reasoning-card">
      <Lightbulb size={28} />
      <h2>Start with your idea.</h2>
      <p>
        What approach would you try, why does it fit, and what should remain
        true—or which edge case matters?
      </p>
      <label htmlFor="reasoning">
        A few plain-language sentences are enough.
      </label>
      <textarea
        id="reasoning"
        rows={6}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="I would try… because… One thing to check is…"
      />
      <details>
        <summary>Recall self-report</summary>
        <select
          aria-label="Recall self-report"
          value={quality}
          onChange={(e) => setQuality(e.target.value)}
        >
          <option value="complete">I reconstructed the core approach</option>
          <option value="partial">I recalled part of it</option>
          <option value="failed">I don't know the approach yet</option>
          <option value="novel">
            This is my first approach to a new problem
          </option>
        </select>
      </details>
      <div className="button-row">
        <button
          className="primary"
          disabled={busy || !answer.trim()}
          onClick={submit}
        >
          Record idea & open editor
          <ArrowRight size={16} />
        </button>
        <button
          className="text-button"
          onClick={() => {
            setAnswer("I don't know the approach yet.");
            setQuality("failed");
          }}
        >
          I don’t know yet
        </button>
      </div>
    </div>
  );
}
