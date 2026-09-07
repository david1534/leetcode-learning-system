# Practice Room

A local Python practice app for learning algorithms with Codex coaching. Start with an independent idea, write and test code, and keep a small amount of useful evidence. Practice Room uses the existing Git history and FSRS scheduler.

## Start on Windows

Install Python 3.11 or newer and Git. A source checkout also needs Node.js 22.12 or newer for its first interface build. Open **Start Study.cmd** in this repository. It prepares a local environment and opens `http://127.0.0.1:8765`. Keep its terminal open while practicing; closing it stops the app. Subsequent launches work offline once dependencies and the interface are installed.

You can also use `python -m pip install -e ".[dev]"`, build the interface with `npm ci` and `npm run build` inside `frontend`, then run `study app`. The interface and API share one loopback origin. The app has no embedded AI service, API key, analytics, CDN, or external font dependency. Your coach remains in Codex.

[Read the daily workflow and recovery guide](WORKFLOW_GUIDE.md). [Coach instructions](AGENTS.md) use the same session operations.

## Foundation release

38 original exercises: five diagnostics; seven Arrays & Hashing core exercises, three transfer variants, and two optional warm-ups; seven items each for Two Pointers, Stack, and Binary Search. Each new topic includes a worked example, incomplete example, three core exercises, and two assessment variants. Later roadmap topics are marked planned.

Every exercise has public examples, edge cases, a reference solution, known-wrong implementations, a hint ladder, prerequisites, stable skills, and a rubric. References and hidden cases are authoring material; Codex should use `study summary` during assessment.

## Evidence that means something

Learn, Recall, Implement, and Transfer are separate activities. Outline recall never extends a full implementation interval. Ready to advance requires independent anchor implementations. Retained requires two independent implementations at least seven elapsed days apart on every core exercise, plus an unseen transfer pass. Assisted and unsuccessful work remain valuable study time without becoming independent success evidence.

The first 12 main sessions establish a prospective baseline. Progress shows sample counts, assistance levels, delayed implementation after at least 24 hours, unseen transfer, and time by activity phase. Routine completion aims for a median of no more than three minutes. This is a product target, not an established optimum or a claim of improved learning.

## Development

- Python: `python -m pytest` and `python -m ruff check --no-cache .`
- Interface, in `frontend`: `npm ci`, `npm test`, `npm run build`, `npm run format:check`
- Windows and Linux checks are configured in `.github/workflows/quality.yml`.
- Candidate checks run in a separate process with a ten-second limit and a Stop control. This is interruption protection, not an operating-system security sandbox; run your own practice code.
- See [implementation and validation notes](docs/RELEASE_NOTES.md) for schema and migration details.
