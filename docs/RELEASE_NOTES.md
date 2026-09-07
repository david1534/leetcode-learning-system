# Foundation app release (0.2.0)

## Behavior

A FastAPI service and React/TypeScript/Monaco interface now share the CLI’s durable study session. Today, Practice, and Progress consolidate selection, reasoning, saved code, interruptible tests, hints, repairs, completion, and evidence. No AI service is embedded; coaching stays in Codex.

The learning policy separates Learn, Recall, Implement, and first-exposure Transfer. FSRS still uses 6.3.2 at 0.9 retention; only implementation/transfer reviews affect its implementation cards. Hard means successful independent recall. Help that supplies missing reasoning requires Again, while implementation, explanation, constraint assessment, and assistance remain separate evidence. Seven elapsed days and an unseen transfer assessment are required for retention; prerequisite anchors control advancement. Relevant repairs use stable skill aliases and a full 24-hour delay.

The foundation catalog contains 38 entries, up from 13. Added topics have worked and faded examples, core implementations, and distinct assessment variants. Validators now require a real codec, all Sudoku uniqueness groups, correct frequency tie-breaking, shortest graph paths, and multiplicity-preserving anagram keys. Every reference passes and every supplied counterexample is rejected.

## Persistence and migration

Session schema 6 introduces revisions, content and rubric versions, activity, exposure, code digests, and phase timing. Review schema 4 adds separate assessment dimensions and the scheduler configuration. Older review IDs, corrections, ratings, solutions, and reflections are not rewritten. Legacy unknowns do not become independent assessment evidence. An active legacy session is upgraded when resumed, and missing exposure evidence remains unknown.

Session writes use atomic replacement and a process-level file lock. Browser drafts survive failed saves, and competing code changes receive a conflict response. Checks run a fixed code snapshot; results carry its digest and stale checks cannot authorize completion. Ten-second timeouts and Stop terminate the candidate process while preserving source.

Each completion stores its code, session, and reflection in a unique archive and uses its session ID as the review ID. A durable receipt permits restart recovery and idempotent publication. Local completion precedes Git operations. Failed publication remains pending. Multiple locally completed sessions can be explicitly published together while preserving individual reviews and reflections. Divergent draft branches are preserved and require a deliberate selection.

## Validation

Run `python -m pytest`, `python -m ruff check --no-cache .`, and the frontend test, build, and formatting commands in README. Tests cover contracts and counterexamples, completion with supplied/calculated minutes and cancellation, subprocess interruption, stale code, shared-session conflicts, elapsed spacing, prior transfer exposure, queue rotation and prerequisites, offline completion, two-computer resume, divergent branches, and publication retries.

The Windows launcher was exercised with a fresh local environment and setup checks. Manual browser checks used an isolated copy: dashboard startup, reasoning before editor access, autosave, stopping an infinite loop, a passing solution check, completion cancellation, local completion, and progress counts. No test activity was added to the learner’s repository history. CI now runs on Windows and Linux; remote CI results are separate from the local Windows checks.

The current FastAPI test-client dependency emits two deprecation notices. They do not fail tests. Vite reports a large editor bundle; Monaco and its worker are served locally and require no runtime CDN. The candidate process has interruption limits but is not a security sandbox for hostile programs.

## Initial measurement policy

The first 12 modern main sessions establish a prospective baseline. Report independent implementation and delayed implementation counts, unseen-transfer counts, assistance, phase timing, and the median completion administration. The initial administration target is at most three minutes. Old history has no comparable transfer baseline and incomplete repair timing, so this release makes no measured claim of better learning per hour.

The 60-minute budget, 45-minute break suggestion, seven-day retention threshold, and review/new rotation are adjustable product policies, not experimentally established optima. The design is informed by retrieval and distributed-practice research, worked-example fading, and interleaving; applying those findings to this curriculum remains an inference to evaluate.

References: [learning techniques review](https://doi.org/10.1177/1529100612453266), [worked-example fading](https://asu.elsevierpure.com/en/publications/transitioning-from-studying-examples-to-solving-problems-effects-/), [interleaving study](https://eric.ed.gov/?id=EJ1237752), [AI-assisted learning and independent assessment](https://doi.org/10.1073/pnas.2422633122), [Anki rating guidance](https://docs.ankiweb.net/studying.html), [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs).
