# LeetCode Learning System

A NeetCode-inspired learning path that is local, testable, and designed for durable recall.
It combines original Python exercises, links to related free LeetCode practice, Socratic AI
coaching, and an FSRS spaced-repetition queue.

## How it works

The roadmap starts with foundational structures and repeatedly revisits older patterns. A normal
45-minute session is 5 minutes of recall, 25 minutes of coding, 10 minutes of explanation/testing,
and 5 minutes of rating and synchronization. New material is intended for weekdays; reviews can
be due any day.

`roadmap -> daily queue -> attempt -> test/hints -> recall rating -> next review`

Ratings have consistent meanings:

- **Again:** you could not reconstruct a working approach.
- **Hard:** you needed major help or substantial debugging.
- **Good:** you passed with at most one hint and explained the complexity correctly.
- **Easy:** you solved it quickly and independently with a correct explanation.

The underlying learning ideas are retrieval practice, spaced repetition, and interleaving. FSRS
adapts future review dates from your ratings instead of using a fixed calendar.

## Setup

Python 3.11 or newer and Git are required.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m study doctor
python -m study today
```

VS Code users can run the included tasks from **Terminal > Run Task**.

## Daily workflow

```powershell
git pull --rebase
python -m study today
python -m study start arrays-001-pair-sum
python -m study hint
python -m study test
python -m study finish --rating good --minutes 35 --explained
git add curriculum progress solutions src tests .github .vscode AGENTS.md README.md pyproject.toml
git commit -m "study: complete pair sum review"
git push
```

`start` creates `.practice/current.py`, which is deliberately ignored by Git. Edit that file in
VS Code. `finish` records an immutable review event and promotes passing work to `solutions/`.
An `Again` rating may be recorded after a failed test; stronger ratings require all tests to pass.
Good and Easy also require `--explained`; Good permits at most one hint and Easy permits none.

Use `python -m study status` for roadmap progress and `python -m study reminder` to preview the
text used by the daily GitHub issue.

Because some OneDrive policies block tool caches, the documented quality command is
`ruff check --no-cache .`.

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

## Public-repository safety

Only code, hint counts, ratings, dates, and mastery progress are tracked. `.practice/` and private
reflections stay local. Before the first public commit, configure a repository-local personal
GitHub identity—prefer the GitHub-provided `noreply` address—and verify `git log` does not expose
an employer email.
