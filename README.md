# Practice Room

A local Python practice app for learning algorithms with Codex coaching. Start with an independent idea, write and test code, and keep a small amount of useful evidence. Practice Room uses the existing Git history and FSRS scheduler.

## Start on Windows

Install Python 3.11 or newer and Git. A source checkout also needs Node.js 22.12 or newer for its first interface build. Open **Start Study.cmd** in this repository. It prepares a local environment and opens `http://127.0.0.1:8765`. Keep its terminal open while practicing; closing it stops the app. Subsequent launches work offline once dependencies and the interface are installed.

You can also use `python -m pip install -e ".[dev]"`, build the interface with `npm ci` and `npm run build` inside `frontend`, then run `study app`. The interface and API share one loopback origin. Outside this repository, use `study --root <repository> app`; discovery never falls back to an installed checkout.

Dark mode is the first-launch default. Settings offer Dark, Light, and System. Monaco loads when you open the editor. Interface assets are local, including fonts and the editor worker.

## Connect coaching

Choose **Connect Codex**, follow **Sign in with ChatGPT**, then refresh the connection. Practice Room uses its own Codex-managed login and private working directory. It does not copy desktop credentials or change global Codex settings. The adapter currently supports **Codex CLI 0.153.4** (`npm install -g @openai/codex@0.153.4` if needed). Other versions disable coaching until validated; saving and practice continue.

Coaching uses your ChatGPT plan’s included Codex allowance, shared with other Codex use. At 20% remaining, automatic checkpoints pause; manual questions remain available. Exhausted or unknown allowance blocks new turns until refreshed. The integration never invokes API billing, purchases credits, or redeems resets. OpenAI controls account credits and allowances, so this is not an unlimited-free-use guarantee. See [authentication](https://learn.chatgpt.com/docs/auth), [App Server](https://learn.chatgpt.com/docs/app-server), and [usage](https://learn.chatgpt.com/docs/pricing).

The coach receives a restricted session projection and returns validated proposals. Shell execution, file edits, browsers, connectors, personal memory, and delegation are disabled and checked at connection. During assessment, conceptual help requires **Switch to guided practice**. Proposed code requires a preview and **Apply**. App conversations stay in `.study-local/coach`; Codex-managed authentication and its working folder live outside the repository under the computer's application-data folder (`PracticeRoom/coach`). Only reviewed learning artifacts are published.

[Read the daily workflow and recovery guide](WORKFLOW_GUIDE.md). [Coach instructions](AGENTS.md) use the same session operations.

## Foundation release

38 original exercises: five diagnostics; seven Arrays & Hashing core exercises, three transfer variants, and two optional warm-ups; seven items each for Two Pointers, Stack, and Binary Search. Each new topic includes a worked example, incomplete example, three core exercises, and two assessment variants. Later roadmap topics are marked planned.

Every exercise has public examples, edge cases, a reference solution, known-wrong implementations, a hint ladder, prerequisites, stable skills, and a rubric. References and hidden cases are authoring material; Codex should use `study coach-context` during assessment.

## Evidence that means something

Learn, Recall, Implement, and Transfer are separate activities. Outline recall never extends a full implementation interval. Ready to advance requires independent anchor implementations. Retained requires two independent implementations at least seven elapsed days apart on every core exercise, plus an unseen transfer pass. Assisted and unsuccessful work remain valuable study time without becoming independent success evidence.

The next 12 completed guided sessions in workflow version 3 establish a separate prospective baseline. Supporting exercises and retries do not inflate it. Progress shows sample counts, assistance levels, delayed implementation after at least 24 hours, unseen transfer, time by phase, and coaching latency and interruptions. Routine completion aims for a median of no more than three minutes. These are descriptive measurements and product targets, not proof of improved learning.

## Development

- Python: `python -m pytest` and `python -m ruff check --no-cache .`
- Interface, in `frontend`: `npm ci`, `npm test`, `npm run build`, `npm run format:check`
- Browser journeys: `npx playwright install chromium`, then `npm run test:browser`. They use disposable repositories and a deterministic fake Codex process, with no account or model allowance.
- Windows and Linux checks are configured in `.github/workflows/quality.yml`.
- Candidate checks run in a separate process with a ten-second limit and a Stop control. This is interruption protection, not an operating-system security sandbox; run your own practice code.
- See [implementation and validation notes](docs/RELEASE_NOTES.md) for schema and migration details.
