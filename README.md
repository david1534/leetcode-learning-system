# Practice Room

A local browser app for daily algorithm practice. Work on one problem, reconstruct an idea, write and test code, and save a brief record. Reviews use the existing FSRS schedule. Coaching is optional and supports personal ChatGPT or a separately configured company provider.

## Start on Windows

Install Python 3.11+, Git, and Node.js 22.12+ (LTS). Open **Start Study.cmd**. The launcher prepares the environment and interface, starts the app in the background, and opens the browser after the server is ready. You can close the launcher window. Subsequent launches reuse the running app or restart an outdated instance while preserving saved work. Another application's occupied port is left alone.

After pulling an update, reopen **Start Study.cmd**. For the first upgrade from version 0.3, close the old Practice Room terminal before launching version 0.4.

The daily workflow and recovery instructions are in [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md).

## A simpler daily session

- **Start / Resume** opens one problem or repair. Reviews happen between sessions.
- The prompt, function, constraints, and public examples stay alongside your work on a laptop and above it on narrow screens.
- Record one short initial idea. “I don't know yet” is valid. Ask for help when you need it; assistance is recorded. Explicit independent assessments preserve the pre-help attempt before conceptual help.
- **Check solution** tests a fixed copy of the saved code. **Stop tests** and **Stop coach** are separate controls.
- **Finish locally** saves the session in one transaction. A short takeaway is optional. Confirm recall once in the completion summary; unknown recall does not change the scheduling interval.
- **Publish & finish**, or **Review & publish** later, explicitly publishes the displayed learning artifacts. A pending publication does not prevent the next local practice.

## Saved on this computer

Version 0.4 stores practice in SQLite under `%LOCALAPPDATA%\PracticeRoom\workspaces\<workspace-id>\practice.sqlite3`, outside the repository and OneDrive. On Linux it uses `$XDG_DATA_HOME/PracticeRoom` or `~/.local/share/PracticeRoom`.

Existing attempts, public history, corrections, and interrupted grouped sessions are imported without deleting their original files. Conflicting versions are retained for recovery. Historical IDs and scheduling evidence stay intact. The repository's `attempt/` files become legacy import material; current practice lives in the local database.

Git exports run in a separate application-data checkout. Saving does not depend on GitHub, changing the source branch, deleting an attempt directory, or receiving a coach response. Pause or Sync backs up the scoped draft for another computer. Check the synchronization result before changing computers. Browser recovery protects unsent edits and offers a download when a save cannot be confirmed.

## Connect coaching

Open **Settings → Coaching connection**. On a new installation, review the suggested Personal ChatGPT or Company connection and save your choice. Existing personal sign-in and coaching history retain Personal. The selected connection stays local to each computer.

- **Personal ChatGPT:** choose **Connect Codex**, then **Sign in with ChatGPT**. Existing sign-in and conversations remain in their original location. Included Codex allowance is shared with your other personal Codex use; unknown or exhausted allowance blocks new personal coaching turns.
- **Company:** enter the HTTPS API base URL, model, reasoning effort, credential environment-variable name, and optional organization ID. **Use detected settings** offers an editable snapshot from local Codex configuration. Save these independent settings, then connect. Enter an environment-variable name such as `OPENAI_API_KEY`, never a credential value. After setting the variable in your terminal, run `Start Study.cmd app --restart` from that terminal so the server receives the updated environment. Usage is managed by your organization.

The app installs its own pinned **Codex CLI 0.157.0** and verifies a restricted configuration for each connection. Company authentication is supplied only to the child process; personal OAuth remains Codex-managed. Global Codex settings are not changed. The app never switches providers after a connection failure. Local practice remains available.

Automatic coaching starts off for a new connection. Model, effort, and automatic-checkpoint preferences are saved separately. Personal automatic checkpoints pause at 20% remaining allowance. Stop or finish a running reply before changing connections. Each connection keeps its own conversation; your code and learning evidence continue in the same attempt.

The coach receives the problem, your recorded idea, current code, and limited check results. Tools and direct file access are disabled. Proposed code needs a preview and **Apply**. Conversations, runtime logs, and authentication stay private; publication includes only the reviewed learning artifacts.

## Learning evidence

The foundation contains 38 original exercises across diagnostics, Arrays & Hashing, Two Pointers, Stack, and Binary Search. Later topics remain planned. Existing curriculum, prerequisites, repair delays, and FSRS parameters are preserved.

Passing tests establishes tested correctness. Recall, explanation, complexity, and assistance are recorded separately. Retention and unfamiliar transfer require repeated evidence. Workflow version 4 tracks one-problem sessions separately from historical grouped sessions; its descriptive metrics do not establish a causal learning improvement.

## Development

- Python: `python -m pip install -e ".[dev]"`, `python -m pytest`, `python -m ruff check --no-cache .`.
- Interface: in `frontend`, run `npm ci`, `npm test`, `npm run build`, and `npm run format:check`.
- Browser journeys: `npx playwright install chromium`, then `npm run test:browser` in `frontend`. Set `PRACTICE_ROOM_TEST_PORT` when another local app uses the default port 8767.
- Tests use disposable repositories and private data directories. Ordinary tests disable the native coach and use a deterministic JSONL fake. Real launcher tests start and stop only their own local server processes.

See [architecture and validation](docs/architecture.md) for persistence, migration, API, synchronization, and release checks. A personal-account coaching smoke check on the Yoga is a separate release acceptance step; mocked coaching and an unauthenticated protocol probe do not establish that it passed.