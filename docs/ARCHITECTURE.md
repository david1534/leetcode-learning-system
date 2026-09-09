# Architecture and storage

Practice Room 0.3.1 provides a web app and terminal commands over one durable study service. The restructuring introduced a guided parent session and optional embedded coaching while preserving the repository's learning records. The 0.3.1 reliability update strengthens timing, revision handling, runtime discovery, and startup without changing assessment policy.

Use the [README](../README.md) to launch the app and the [workflow guide](../WORKFLOW_GUIDE.md) for learner-facing behavior. This document describes where that behavior belongs in the code.

## Application boundaries

| Component | Responsibility |
| --- | --- |
| `frontend/src/App.tsx` | Today, Practice, Progress, settings, and completion interactions. |
| `frontend/src/useWorkspace.ts` | Fetching state, ordered actions, autosave, competing edits, coaching requests, and recovery. |
| `frontend/src/useStudyClock.ts` | Continuous browser clock between authoritative state samples; pause, resume, session, and timing reconciliation. |
| `frontend/src/Editor.tsx` | Lazy-loaded Monaco editor and editor state. |
| `frontend/src/CoachPanel.tsx`, `CoachConnection.tsx` | Coaching conversation, assessment conversion, proposals, connection status, and sign-in controls. |
| `frontend/src/persistence.ts`, `theme.ts` | Browser draft storage, exports, and appearance preferences. |
| `src/study/app.py` | Local HTTP API, static interface serving, coaching status events, and server startup/shutdown. |
| `src/study/cli.py`, `commands.py` | Command parsing and dispatch into shared operations. |
| `src/study/service.py` | `StudyService`: locked session mutations, code revision checks, testing, completion, publication, and recovery. |
| `src/study/guided.py` | `GuidedSession` operations mixed into `StudyService`: parent stages, supporting work, repair drafts, timing, conversion, and the restricted coach projection. |
| `src/study/coach.py` | Coaching lifecycle, allowance checks, request identities, response validation, assistance findings, and approved code proposals. |
| `src/study/codex_runtime.py` | Supported CLI discovery and the owned, restricted App Server process and protocol. |
| `src/study/interfaces.py` | Typed inputs for shared application operations. |
| `src/study/core.py`, `policy.py` | Curriculum, learning evidence, FSRS scheduling, eligibility, queues, and progress calculations. |
| `src/study/runner.py`, `worker.py` | Candidate execution with time limits and interruption. |
| `src/study/storage.py`, `gitflow.py` | Atomic file replacement and scoped Git operations. |

The web interface and CLI must use `StudyService` for mutations. Embedded coaching obtains the restricted projection from that service; it must not open reference or hidden assessment material to construct a parallel view of the session.

## State and request flow

1. Today asks the service for eligible work. Starting or resuming creates or restores a guided parent session with its stages and shared budget.
2. The browser receives a state projection with an observation timestamp, session revision, code digest, and elapsed time. Browser interpolation updates the display; the service owns recorded time and uncertain-gap recovery.
3. Edits remain in browser storage when available while autosave sends code, exercise ID, revision, and digest. Another writer's changes require a deliberate conflict choice.
4. Normal actions run in order and read revisions when dispatched. Older state responses are ignored. Stop-test, stop-repair, coaching interruption, and disconnect actions can bypass the ordinary action queue.
5. Candidate checks use a fixed code snapshot. Changed code invalidates the prior result for completion purposes. Coaching requests similarly carry the session and code identity; uncertain acknowledgements retain their request ID until reconciled.
6. Local completion writes the durable evidence and recovery receipt. Public publication is a separate explicit operation using only the approved learning paths.

The browser polls study state and receives coaching status through server-sent events. API responses use `Cache-Control: no-store`. Browser API calls time out after 60 seconds with recovery guidance; a timeout does not prove that the server rejected a mutation.

## Storage and portability

| Location | Contents and handling |
| --- | --- |
| `curriculum/` | Exercise catalog, roadmap, and authoring validation material. Do not expose reference/hidden cases during assessment. |
| `attempt/` | Current candidate and durable session; scoped pause snapshots can include the guided parent, repair, and supporting artifacts for another computer. |
| `progress/reviews/`, `progress/corrections/`, `progress/learning-events/` | Durable review, correction, error, and repair evidence. Preserve existing identities and historical meaning. |
| `progress/attempts/`, `progress/orphan-drafts/` | Completed-attempt archives and recovered sessionless code, created when needed. |
| `solutions/`, `reflections/` | Promoted passing implementations and durable learning reflections. |
| `.study-local/` | Ignored locks, timer checkpoints, check state, synchronization state, completion receipts, and recovery/conflict copies. |
| `.study-local/coach/` | Ignored conversation, request, and coaching preference data. Never include it in public learning history. |
| Browser local storage | Drafts and interface preferences for that browser origin. This is not cross-computer synchronization. |
| External `PracticeRoom/coach/<workspace-key>/` | Codex-managed home/login and restricted working directory, outside the checkout. Each checkout path has a separate workspace key. |
| `.venv/`, `frontend/node_modules/`, `src/study/web/` | Generated environment, frontend dependencies, and production assets. They are ignored by Git. |

On Windows, the private runtime defaults to `%LOCALAPPDATA%`; other environments use `XDG_DATA_HOME` or `~/.local/share`. An explicit `PRACTICE_ROOM_PRIVATE_HOME` relocates the private data root, which must remain outside the study checkout. It is a development/configuration option, not an alternative authentication mechanism.

Historical learning files intentionally disable Git line-ending normalization in `.gitattributes`. Preserve their bytes when checking out or packaging; do not “fix” old CRLF records as a source-formatting change. Generated local receipts and browser drafts do not replace a successful scoped pause/sync before changing computers.

## Build and launch

`Start Study.cmd` delegates to `scripts/study.ps1`. The launcher prepares `.venv`, checks dependency changes using the `pyproject.toml` hash, and builds changed interface inputs. Vite writes the production build to `src/study/web/`, which FastAPI serves with the API on loopback port 8765. Generated assets should never be edited by hand or committed as the source of a UI change.

The launcher recognizes a running app for the same workspace and version. Another workspace needs a different port; an older version needs a restart. See [troubleshooting](TROUBLESHOOTING.md) for exact commands.

## Development and validation

Use a disposable checkout or copied fixture for study actions during development. Read [AGENTS.md](../AGENTS.md) before changing learning policy or persistence. Tests must never discover or mutate a real learner workspace.

With the development Python environment active, run from the repository root:

```text
python -m pytest
python -m ruff check --no-cache .
python -m ruff format --check src tests
```

Then run the interface checks from `frontend/` in this order:

```text
npm ci
npm test
npm run format:check
npm run build
npx playwright install chromium
npm run test:browser
```

Finish the production build before starting browser journeys. The test server decides whether built assets are present when it starts. Playwright uses the repository's `.venv` Python when present, otherwise `python` from PATH. The server in `tests/browser_server.py` uses disposable repositories and `tests/fake_codex.py`, never a signed-in coaching account.

The Windows launcher's `_quality` action and VS Code's **Quality: Full Suite** task run these checks together. The [GitHub workflow](../.github/workflows/quality.yml) runs Python 3.13 and Node 24 on Windows and Linux and installs Chromium's system dependencies where needed. Browser traces are uploaded on failure. `tests/conftest.py` adds an audit guard against writes to the actual learner artifacts.

Version 0.3.1's reviewed implementation passed 152 Python tests, eight interface tests, and 17 browser journeys on the [Windows/Linux validation run](https://github.com/david1534/leetcode-learning-system/actions/runs/34374952035). A live signed-in coaching conversation is a separately authorized check. The real runtime review covered discovery and restricted initialization only. See [release notes](RELEASE_NOTES.md) for known limits.
