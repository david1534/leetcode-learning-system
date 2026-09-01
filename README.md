# LeetCode Learning System

A NeetCode-inspired learning path that is local, testable, and designed for durable recall.
It combines original Python exercises, links to related free LeetCode practice, Socratic AI
coaching, and an FSRS spaced-repetition queue.

For the complete day-to-day instructions and command reference, see
**[How to Use the Learning Workflow](WORKFLOW_GUIDE.md)**.

## How it works

The roadmap starts with foundational structures and repeatedly revisits older patterns. A normal
45-minute session is 5 minutes of recall, 25 minutes of coding, 10 minutes of explanation/testing,
and 5 minutes of rating and synchronization. New material is intended for weekdays; reviews can
be due any day.

`roadmap -> daily queue -> attempt -> local coaching checks -> recall rating -> next review`

Ratings have consistent meanings:

- **Again:** you could not reconstruct the core approach or substantial help supplied its pattern,
  invariant, representation, pseudocode, or multi-step construction.
- **Hard:** you retained the core algorithm but needed guided refinement or substantial debugging.
- **Good:** you solved it with no algorithmic help, though extra time or checkpoints were needed.
- **Easy:** you solved it quickly and independently with a correct explanation.

The underlying learning ideas are retrieval practice, spaced repetition, interleaving, desirable
difficulty, rapid corrective feedback, and transfer. FSRS adapts future review dates from your
ratings instead of using a fixed calendar.

## Setup

Python 3.11 or newer, Git, and VS Code are required. Open the cloned repository in VS Code and
press `Ctrl+Shift+B`. The first run creates `.venv` and installs the required packages for you.

To verify or repair setup manually:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m study doctor
```

VS Code users can run the included tasks from **Terminal > Run Task**.

The normal daily entry point is `Ctrl+Shift+B`. It safely updates from GitHub, resumes a public
attempt branch when one exists, otherwise starts the oldest due review or next roadmap problem,
and opens the candidate. You never need to copy a problem ID or remember a Python command.
If an editor recreates an already-published candidate after completion, startup safely removes it
and generated caches; any unmatched or unrecognized attempt file is preserved and reported.

## Daily workflow

1. Press `Ctrl+Shift+B`. Before opening code, reconstruct the likely pattern, why it fits, its
   invariant, expected complexity, and one important edge case. Reviews label this retrieval as
   complete, partial, or failed.
2. Record that compact plan; the candidate then opens for clean implementation.
3. Tell Codex **"give me a hint"** or run **Study: Next Hint** when needed. Retry after every hint.
4. Tell Codex **"test my solution"** or run **Study: Check Solution Locally**. Deterministic cases
   verify correctness locally, then Codex discusses one issue at a time without exposing hidden
   inputs. Nothing is pushed during a check.
5. Tell Codex **"pause my practice"** before changing laptops.
6. Tell Codex **"I'm finished"**. Codex drafts the reflection from your conversation and code;
   correct it if needed, confirm the recommended recall rating and minutes, and explicitly approve
   publication. Codex records the review/reflection and merges it into `main`.

Codex records your initial reasoning and each material coaching intervention in the tracked attempt.
Those facts survive pauses and device changes, appear in the published reflection, and enforce the
highest honest rating. Passing tests cannot override substantial help: that review is Again.

If Codex is unavailable, run **Study: Finish Session** for the guided terminal fallback.

Use the **Study: Status** VS Code task for roadmap progress.

The workflow records sanitized error events by skill, category, cause, and severity. A blocking
misconception—or the same minor error recurring—creates a next-day repair gate. The gate asks for
the recognition trigger, corrected rule, why the earlier reasoning failed, and application to an
original scenario. Due reviews can continue, but new curriculum work waits for an independent
repair. Run `python -m study insights` for recall, assistance, first-checkpoint, and error trends.

At 45 active minutes the system recommends a break. Productive work can be explicitly extended in
short blocks with `python -m study continue --minutes 10`; the boundary is deliberately soft.

These choices follow robust findings from retrieval-practice, distributed-practice, interleaving,
and effective-learning-technique research (Roediger & Karpicke; Cepeda et al.; Rohrer & Taylor;
Dunlosky et al.). The design optimizes independent interview transfer per active hour rather than
problem counts or streaks.

Because some OneDrive policies block tool caches, the documented quality command is
`ruff check --no-cache .`.

### Recovery and advanced commands

Normal study does not require these commands. If GitHub was temporarily unavailable, run the
**Study: Pause & Sync** task again or use `python -m study sync`. If a completed attempt was
committed but could not merge, use `python -m study sync --complete`. The system never force-pushes,
discards candidate code, resolves conflicts, or includes unrelated files automatically.

## Curriculum

1. Foundations: Python collections, arrays and hashing, two pointers, stacks, binary search.
2. Linear patterns: sliding windows, linked lists, intervals.
3. Hierarchical search: trees, heaps, tries, backtracking.
4. Graphs and optimization: graphs, advanced graphs, greedy, 1-D dynamic programming.
5. Advanced synthesis: 2-D dynamic programming, bit manipulation, math/geometry, mixed sets.

The initial library contains an optional five-question diagnostic and the complete Arrays &
Hashing foundation module. A module is mastered only after all core solutions pass, every core
problem earns Good/Easy reviews on two separate dates, a transfer exercise passes, and the learner
can explain the approach and complexity.

## Future Codex sessions

Open Codex from the repository root. Codex automatically reads `AGENTS.md`, inspects the current
queue, resumes incomplete work, and follows the hint ladder without immediately giving away a
solution. Ask it to start today's session, review your approach, or generate the next roadmap
exercise. Durable state lives in Git, not in a particular chat.

## Cross-device reminders

The GitHub Actions workflow runs at both possible UTC equivalents of 8:00 AM Eastern, guards on
the actual `America/New_York` hour, closes earlier open reminder issues, and creates today's issue.
Enable GitHub watch/email/mobile notifications after publishing. Scheduled workflows can be a few
minutes late and GitHub may disable schedules after prolonged repository inactivity.

## GitHub automation

**Code quality** runs the full test suite and Ruff after pushes and pull requests to protect `main`.
**Daily practice reminder** runs at both UTC hours that can correspond to 8:00 AM Eastern, then
creates an issue only when the Eastern-time guard matches. The other scheduled run is an intentional
no-op for daylight-saving compatibility. Each workflow writes a summary explaining its outcome.

## Public-repository safety

Draft code synchronized at start/pause, hint counts, checkpoint summaries synchronized at pause,
ratings, dates, and full learning reflections are public by design. Intermediate checks, failed
inputs, and error details stay local. Before the first public commit,
configure a repository-local personal
GitHub identity—prefer the GitHub-provided `noreply` address—and verify `git log` does not expose
an employer email.
