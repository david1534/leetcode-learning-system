# Practice Room

A local algorithm-learning app with a Python service, a React editor, and optional Codex coaching. Start with an independent idea, write and test code, and keep a brief record of what you learned. The web app, terminal commands, and coach share one durable study session and the existing Git history and FSRS scheduler.

**Current release: 0.3.1.** This update fixes timer jumps, Windows Codex discovery, delayed-response and autosave conflicts, keyboard navigation, and first-run/update handling. See the [release notes](docs/RELEASE_NOTES.md) for changes and validation limits.

## Start on Windows

Install Python 3.11 or newer and Git. A source checkout also needs Node.js 22.12 or newer to build the interface. Internet access is needed for the initial dependency installation.

1. Clone this repository, or open your existing Git checkout.
2. Double-click **Start Study.cmd**. It creates the local Python environment, installs dependencies, and builds the interface when needed.
3. Keep the terminal open. The app opens at `http://127.0.0.1:8765`; closing its terminal stops the server.
4. Choose your budget on **Today**, then **Start practice** or resume the saved session.

In VS Code, **Ctrl+Shift+B** runs the same launcher. Once dependencies and the interface are installed, local practice works offline. Coaching and remote synchronization require a connection. A preview archive with a built interface can run locally, but Git synchronization requires a Git checkout.

### Update an existing installation

Save or pause your current work, close the running app terminal, and update the checkout to the reviewed release without discarding local changes. Reopen **Start Study.cmd**. It refreshes changed Python dependencies and rebuilds changed interface inputs. An older server still using the port asks you to restart it.

Keep your existing study folder and recovery files. Replacing it with a new download does not bring over unpublished work or browser drafts. See [updating and recovery](docs/TROUBLESHOOTING.md#updating-without-losing-work).

### Manual setup

From the repository root, create and activate a Python virtual environment, then run:

```text
python -m pip install -e ".[dev]"
cd frontend
npm ci
npm run build
cd ..
python -m study app
```

These steps also provide a manual launch path on Linux and macOS. Windows and Linux are covered by automated checks. Outside the checkout, pass the root explicitly: `python -m study --root <repository> app`. The service listens on loopback only. Run `python -m study app --help` for port and browser-opening options.

## The daily workspace

| Area | What it does |
| --- | --- |
| Today | Select a budget, see the next activity and due reviews, resume work, and inspect synchronization status. |
| Practice | Record an initial idea, code in the local Monaco editor, run or stop tests, use optional coaching, and finish or pause. |
| Progress | Review attempts, assistance, delayed independent performance, topic readiness, and time spent. |
| Settings | Choose Dark, Light, or System appearance and connect or refresh Codex. |

One guided session groups supporting retrieval or a repair, the main exercise, and a single completion summary. The shared timer includes reasoning, coding, coaching, repairs, and administration; use **Pause** when you stop. Routine polling no longer restarts the display clock. Problem, Code, and Coach panels adapt to the available width and support keyboard navigation. Dark mode is the first-launch default, and the editor loads when needed.

Drafts are saved locally and backed up in browser storage when available. Competing edits require an explicit choice. **Finish locally** saves learning evidence; **Publish & finish** is a separate, explicit action that synchronizes the reviewed artifacts. Follow the [daily workflow](WORKFLOW_GUIDE.md) for timing, ratings, repairs, completion, and two-computer use.

## Connect optional Codex coaching

Choose **Connect Codex**, follow **Sign in with ChatGPT**, then choose **Refresh connection**. Practice Room owns a separate Codex-managed login and private working directory; it does not copy your desktop credentials or change global Codex settings.

The adapter validates **Codex CLI 0.153.4**. On Windows it checks PATH, the Codex desktop installation, and the usual npm folder. If no supported installation is found, **Help connecting Codex** shows the setup steps. With Node.js installed, the pinned CLI can be installed using:

```text
npm install -g @openai/codex@0.153.4
```

For a custom installation, set `PRACTICE_ROOM_CODEX` to an existing absolute executable path before launching. Unsupported versions leave local practice available. Connection results are visible in Settings, the coach panel, and repairs. See [connection troubleshooting](docs/TROUBLESHOOTING.md#codex-cannot-connect).

Coaching uses your ChatGPT plan's Codex allowance, shared with other Codex activity. Automatic checkpoints pause at 20% remaining; unknown or exhausted allowance blocks new turns until refreshed. The integration does not use API billing, purchase credits, or redeem resets. OpenAI controls account allowances. See the official [authentication](https://learn.chatgpt.com/docs/auth), [App Server](https://learn.chatgpt.com/docs/app-server), and [usage](https://learn.chatgpt.com/docs/pricing) documentation.

The coach receives a restricted session projection. Execution tools, file edits, browsers, connectors, personal memory, and delegation are disabled and checked at connection. Conceptual help during assessment requires **Switch to guided practice**; proposed code requires a preview and **Apply this change**. Conversations remain local, and only reviewed learning artifacts enter public history.

## Curriculum and learning evidence

The foundation contains 38 original exercises: five diagnostics; seven Arrays & Hashing core exercises, three transfer variants, and two optional warm-ups; and seven exercises each for Two Pointers, Stack, and Binary Search. Later roadmap topics are marked planned. Exercises include public examples, references, edge cases, rejected incorrect implementations, hints, prerequisites, and a skill rubric. References and hidden cases are authoring material; coaching should use `study coach-context` during assessment.

Learn, Recall, Implement, and first-exposure Transfer measure different things. Outline recall does not extend an implementation review interval. Assistance, tested correctness, explanation, complexity, and independent recall remain separate evidence. Retention requires delayed independent implementations and unseen transfer; one pass or same-day repetition does not establish it. Historical ratings and unknown evidence are preserved.

The next 12 completed guided sessions in workflow version 3 form a separate descriptive baseline. Supporting work does not inflate session counts. Progress reports counts alongside rates, time by stage, assistance, and coaching interruptions. These measurements are not a claim of proven learning improvement.

## Repository and development

| Location | Purpose |
| --- | --- |
| `frontend/` | React/TypeScript interface, Monaco editor, unit tests, and browser journeys. |
| `src/study/` | Shared study service, guided workflow, FastAPI app, CLI, coaching adapter, scheduling, and Git synchronization. |
| `curriculum/` | Original exercise catalog, roadmap, and authoring validation data. |
| `progress/`, `solutions/`, `reflections/` | Durable learning records and reviewed artifacts. |
| `scripts/study.ps1`, `Start Study.cmd`, `.vscode/` | Windows launch and development entry points. |
| `tests/`, `.github/workflows/` | Disposable-repository regression tests and Windows/Linux automation. |

The interface builds into ignored `src/study/web/`; edit its source in `frontend/src/`. Active and private recovery state have separate storage rules. See the [architecture and storage guide](docs/ARCHITECTURE.md) before changing session persistence or coaching.

For the full Windows quality check, use **Quality: Full Suite** in VS Code or run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\study.ps1 _quality
```

The [development checks](docs/ARCHITECTURE.md#development-and-validation) list individual commands and build order. The reviewed application passed 152 Python tests, eight interface unit tests, and 17 Chromium browser journeys, with [Windows and Linux checks passing](https://github.com/david1534/leetcode-learning-system/actions/runs/34374952035). Tests use disposable repositories and a deterministic fake Codex process. Live sign-in and model replies are separate checks; the 0.3.1 review verified real CLI discovery and restricted initialization only.

Candidate checks have a ten-second limit and a Stop control. They run your practice code locally and are not an operating-system sandbox for hostile programs.

## Guides

- [Daily workflow and coach commands](WORKFLOW_GUIDE.md)
- [Setup, connection, draft, and timer troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture, storage, and development checks](docs/ARCHITECTURE.md)
- [Release history and validation limits](docs/RELEASE_NOTES.md)
- [Coaching and contribution instructions](AGENTS.md)
