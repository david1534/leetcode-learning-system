# Integrated coaching release (0.3.0)

## Daily practice

Practice Room now starts in dark mode and keeps Today, Practice, Progress, and settings in one local app. The editor opens at the implementation, remembers its position, loads only when needed, and follows the selected theme. Laptop and narrow layouts preserve the problem, editor, and coach through tabs. Errors distinguish browser drafts, conflicting edits, test timeouts, Git synchronization, and coaching availability.

One guided session groups supporting retrieval, an eligible repair, the main activity, and a single completion. The shared clock counts Codex work and all stages, excludes confirmed pauses, and marks sleep/restart gaps for correction. Short sessions omit supporting work. Unseen transfer precedes related warm-ups. Parent sessions drive the review/new rotation and the new 12-session measurement cohort.

Repairs accept one fresh application. Small coding repairs run learner-authored assertions with Stop and a ten-second timeout; these checks do not establish conceptual correctness. Coach judgments and learner confirmation remain labeled separately. Repair pause saves the application before synchronizing its scoped draft; successful completion resumes the next activity.

## Optional Codex coaching

A private, owned App Server process, running outside the curriculum checkout, embeds Codex through ChatGPT sign-in. The verified adapter supports CLI 0.153.4 and checks its restrictive configuration before use. It does not copy credentials, alter global settings, enable execution tools, use API/provider fallback, buy credits, or redeem resets. Unknown/exhausted allowance prevents new turns; at 20% remaining, automatic checkpoints stop while manual questions remain available. Allowance is shared with other Codex activity and controlled by OpenAI.

The coach sees only a versioned session projection. Independent assessment excludes topic cues, hidden cases, reference solutions, and historical solutions. Substantive help requires an explicit transition that preserves the original assessment and code. Guided success cannot retroactively establish an independent transfer pass. More substantive help requires a saved reasoning or code retry; applying a coach proposal does not constitute a learner retry.

Requests have stable IDs, exact code/evidence versions, typed public responses, and private durable status. Completed output is validated before display. Unexpected tool requests disable coaching. Interruptions reconcile the existing conversation rather than blindly resend. Code changes require a visible diff and explicit Apply; stale proposals cannot replace newer work. Conversations remain local and in Codex-managed storage; public history contains approved learning artifacts only.

## Evidence and persistence

Findings retain their source and actual learner evidence. A test pass establishes tested correctness only. Unknown or disputed recall cannot silently become success; unknown recall leaves the scheduling interval unchanged. Again remains missing recall, while Hard is successful independent recall with substantial effort. Implementation, explanation, constraints, and assistance remain separate.

Schema 6 sessions and schema 4 reviews preserve existing IDs and historical ratings. Workflow version 3 adds a parent session, pre-help assessment evidence, coaching measurements, and amendments. Pause carries supporting receipts and artifacts between computers without including raw conversations. Conflicts preserve both versions. Local completion and explicit publication remain separate and publication is idempotent.

An audit test exposed repository discovery falling back to the installed checkout. The affected attempt was recovered as paused, its code and identity preserved, and synthetic evidence quarantined before further work. Discovery now requires a repository ancestor or an explicit root. An audit guard prevents tests from writing to real learning artifacts, and every test runs in a disposable working directory.

## Validation and limits

Python regression checks, interface tests, production build, formatting, and real Playwright journeys cover recovery, revisions, multiple tabs, assistance, conversion, repairs, timeouts, offline practice, and completion. Browser tests use disposable repositories and a deterministic fake Codex process; normal CI consumes no model allowance. The CI matrix runs Windows and Linux.

A live Windows smoke check used ChatGPT sign-in with the restricted CLI 0.153.4 configuration. Representative coaching cases for Arrays & Hashing, Two Pointers, Stack, and Binary Search each returned a brief hint without supplying code or claiming independent success. This is a bounded factual/behavioral review, not a guarantee that future model replies will be error-free.

The full Monaco bundle remains large but is loaded only with the editor; Today and Progress do not download it. Two upstream test-client deprecation notices remain. Candidate execution is interruptible, not an operating-system sandbox for hostile code. The next 12 completed guided sessions measure delayed independent implementation, unseen transfer, total/stage time, administration against a three-minute median target, and coaching interruptions/latency. These measurements are descriptive, not a causal claim of improved learning.

The feature remains a draft pull request until reviewed. No automatic merge or learner-history publication is part of this release.

---

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
