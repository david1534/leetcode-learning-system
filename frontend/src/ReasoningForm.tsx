import { Lightbulb } from "lucide-react";

export default function ReasoningForm({
  answer,
  busy,
  setAnswer,
  submit,
}: {
  answer: string;
  busy: boolean;
  setAnswer: (value: string) => void;
  submit: (answer: string, quality: "unknown" | "failed") => void;
}) {
  return (
    <section className="panel reasoning-card" aria-labelledby="idea-title">
      <Lightbulb size={22} />
      <h2 id="idea-title">What would you try, and why?</h2>
      <p>
        Use the problem and examples alongside this question. A few sentences
        and an important condition or edge case are enough.
      </p>
      <label htmlFor="reasoning">Your initial idea</label>
      <textarea
        id="reasoning"
        rows={5}
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
        placeholder="I would try… because…"
      />
      <div className="button-row">
        <button
          className="primary"
          disabled={busy || !answer.trim()}
          onClick={() => submit(answer, "unknown")}
        >
          Continue to code
        </button>
        <button
          className="text-button"
          disabled={busy}
          onClick={() => submit("I don't know the approach yet.", "failed")}
        >
          I don't know yet
        </button>
      </div>
      <small>
        Your initial idea stays separate from any help you request afterward.
      </small>
    </section>
  );
}
