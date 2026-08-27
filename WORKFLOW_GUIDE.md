# How to Use the Learning Workflow

This is the practical guide for daily use of the repository. The normal workflow is
conversation-first: open Codex from this repository and use the phrases below. VS Code tasks and
Python commands are available as fallbacks.

## Start or resume practice

Open the repository in VS Code, then either:

- Tell Codex: **“Start today’s practice.”**
- Press `Ctrl+Shift+B` to run **Study: Start or Resume**.
- Run `.\.venv\Scripts\python.exe -m study practice --open` from PowerShell.

Startup safely synchronizes with GitHub and follows this priority:

1. Resume the unfinished attempt recorded in `attempt/session.json`.
2. Start the oldest due FSRS review.
3. Start the next roadmap problem when no review is due.

If startup reports a repository blocker, stop and resolve it. Do not replace the repository
activity with an unrelated problem or quiz.

## Reconstruct the approach before coding

Keep `attempt/current.py` closed at first. Explain these five items to Codex:

1. The approach you would try.
2. Why it fits the problem and constraints.
3. The invariant or fact that remains true while the algorithm runs.
4. Expected time and space complexity.
5. One important edge case.

Codex records this blank-slate reasoning before opening the candidate. This distinguishes genuine
recall from an approach learned during the session.

## Work on the solution

Implement your own solution in `attempt/current.py`. Codex will coach the reasoning process but
will not write or replace the candidate unless you explicitly request it.

Use these conversation commands:

| Say this | What happens |
| --- | --- |
| **“Give me a hint.”** | Reveals the next stored hint and records the assistance. Revise and checkpoint before requesting another hint. |
| **“Test my solution.”** | Runs deterministic cases locally and discusses one likely issue at a time. Detailed failures remain local. |
| **“Pause my practice.”** | Pauses active time and synchronizes the tracked attempt branch to GitHub. |
| **“I’m finished.”** | Evaluates the solution and begins the review and publication process described below. |

Equivalent VS Code tasks are **Study: Next Hint**, **Study: Check Solution Locally**, and
**Study: Pause & Sync**.

## Pause or change computers

Before stopping or changing computers, tell Codex **“Pause my practice.”** The repository commits
and pushes only the scoped attempt evidence. On the other computer, open the repository and start
practice normally; the remote attempt branch is detected and resumed.

## Finish and publish

Tell Codex **“I’m finished.”** This does not grant publication approval. Codex will:

1. Run the final deterministic evaluation.
2. Show the evidence-based rating recommendation and calculated active minutes.
3. Draft the approach, invariant, complexities, mistakes and lessons, assistance, and rating
   rationale.
4. Show the complete draft, target repository, rating, minutes, and affected files.
5. Ask for explicit publication confirmation.
6. After confirmation, publish the solution, review, and reflection and merge the attempt into
   `main`.

The rating cannot exceed the available evidence:

- **Easy:** correct, quick, and independently reconstructed.
- **Good:** independently solved, but required extra time or multiple checkpoints.
- **Hard:** the core approach was retained but guided help or partial recall was needed.
- **Again:** the core approach was not reconstructed, or substantial help supplied the pattern,
  representation, invariant, pseudocode, or multi-step construction.

Passing tests establishes eventual correctness; it does not by itself establish independent
recall.

## Repair gates

A blocking misconception, substantial help, or the recurrence of the same minor error can create
a delayed repair gate. Due FSRS reviews remain available, but new curriculum work waits until the
gate is cleared independently.

The practice queue, today view, learning insights, and reminder issue show the repair error ID,
prompt, and the beginning of the required command. The normal path is to ask Codex to guide the
repair conversation. The response covers:

- The recognition trigger.
- The corrected rule.
- Why the earlier reasoning failed.
- Application to a fresh, original scenario.

## Time boundary and learning insights

At 45 active minutes, the workflow recommends a break. If continuing is genuinely productive,
explicitly request a short extension or run:

```powershell
.\.venv\Scripts\python.exe -m study continue --minutes 10
```

To review recall, assistance, first-checkpoint, timing, error, and repair trends, run the
**Study: Learning Insights** task or:

```powershell
.\.venv\Scripts\python.exe -m study insights
```

## Recovery commands

Normal practice should not require these commands:

```powershell
# Retry synchronization after a temporary GitHub failure
.\.venv\Scripts\python.exe -m study sync

# Merge an already committed completion when the earlier merge was interrupted
.\.venv\Scripts\python.exe -m study sync --complete

# Check repository, Git, identity, dependencies, and curriculum setup
.\.venv\Scripts\python.exe -m study doctor
```

The workflow never force-pushes, silently resolves conflicts, or includes unrelated files in a
practice commit.

## Public repository expectations

Attempt branches, candidate code synchronized at start or pause, checkpoint summaries, ratings,
dates, solutions, learning events, and reflections are public by design. Detailed failing inputs
remain local. Do not place credentials, employer email addresses, proprietary problem statements,
or local filesystem paths in public learning artifacts.

## Quick reference

| Goal | Conversation | VS Code or command |
| --- | --- | --- |
| Start or resume | “Start today’s practice.” | `Ctrl+Shift+B` |
| Get one hint | “Give me a hint.” | **Study: Next Hint** |
| Check the candidate | “Test my solution.” | **Study: Check Solution Locally** |
| Pause and synchronize | “Pause my practice.” | **Study: Pause & Sync** |
| Finish | “I’m finished.” | **Study: Finish Session** |
| View progress | Ask for status | **Study: Status** |
| View learning trends | Ask for learning insights | **Study: Learning Insights** |
