# Daily practice

## Open and resume

Open **Start Study.cmd**, run `study app` in the installed environment, or use VS Code's **Study: Start or Resume** task. The launcher opens the browser when the app is ready. Its terminal can close while practice continues. Reopening the launcher reuses the correct server or restarts an outdated one safely. For the first upgrade from version 0.3, close the old foreground server terminal first.

A saved attempt opens with its full problem, constraints, function signature, and public examples. Resume that attempt before starting another. Returning after several days does not create a new review or require repeating an already recorded initial idea. Restart or a long sleep gap pauses uncertain timing so you can correct it at completion.

Each session contains **one problem or repair**. There is no automatic sequence of warm-up, repair, recall, and main activity. Finish returns to Today; another problem starts only when you choose it. The scheduler continues to balance eligible implementation reviews, new material, and unfamiliar transfer. A short Recall session does not replace a full implementation review.

The default time budget is 60 active minutes. A break is suggested at 45 minutes. Pause when stepping away. Browser focus alone is not an activity sensor because coaching time also counts. At the budget boundary, work is preserved and timing pauses; a short explicit extension is available. Correct measured minutes in the completion summary when necessary.

## Work on the problem

The problem remains beside your work on laptop screens and above it on narrow screens. Previous completed answers and hints are not shown automatically.

Start with a few sentences: what you would try, why it fits, and an important condition or edge case. Plain language is enough. **I don't know yet** is a valid initial attempt. The app records the actual answer; it does not assume complete recall. Confirm recall once when finishing.

Write code in the editor. **Saved on this computer** means the database acknowledged the save. **Saved in browser** means the edit is recoverable in this browser but has not been confirmed by the app. If browser storage is unavailable too, keep the page open and use **Download work**.

**Check solution** runs public and assessment cases against a fixed saved candidate. Public-example failures are shown; hidden-case details stay out of coaching context. A timeout or **Stop tests** is distinct from an incorrect answer. Editing the candidate invalidates earlier test evidence; run the check again before treating it as correct. Results wait for other app requests to finish saving. If the checker itself fails, the app shows retry guidance and preserves your code and learning evidence; that failure is not counted as an incorrect solution.

Two windows cannot silently overwrite conflicting drafts. Compare their versions, then deliberately keep your draft or use the other saved version. A changed active problem also rejects an old tab's write. Earlier unsent text is retained in browser recovery.

## Ask for help when needed

Ordinary practice offers help directly after your initial attempt. Use **Ask coach**, **Give me a hint**, or **Study a worked example**. Assistance is recorded according to what it supplied. Try the reasoning or code again before requesting another step of help.

An explicit independent assessment is different: conceptual help first offers **Continue independently** or **Switch to guided practice**. Switching preserves the original assessment and pre-help candidate. Assisted completion cannot become an unseen independent transfer pass.

A worked example preserves your candidate and marks assisted learning. Trace it, explain a step, and then attempt an incomplete example or fresh implementation. A proposed code change is previewed; applying it requires **Apply this change** and a new test run.

Open **Settings → Coaching connection** before connecting. A new installation suggests Personal ChatGPT or Company from local configuration; review and save your choice once. Existing personal sign-in and history retain Personal. The choice and settings stay on this computer.

For **Personal ChatGPT**, choose **Connect Codex** and **Sign in with ChatGPT**. Your existing private sign-in and conversations are preserved. Unknown or exhausted included allowance blocks new personal turns; local practice remains available.

For **Company**, enter the HTTPS API base URL, default model, reasoning effort, credential environment-variable name, and optional organization ID. **Use detected settings** fills an editable snapshot from local Codex settings. After saving, Practice Room uses its independent configuration. Enter only a variable name (for example `OPENAI_API_KEY`), never the key itself; after setting the variable in your terminal, run `Start Study.cmd app --restart` from that terminal so the server receives the updated environment. The organization ID is sent as the provider's organization header. Usage is managed by your organization, without a personal allowance meter. Authentication, model-access, throttling, or connectivity failures remain on Company until you explicitly choose another connection.

Practice Room owns its pinned CLI and verifies restricted personal/company configurations. It leaves global Codex settings alone. **Stop coach** and **Stop tests** control separate processes. Finish or stop a running reply before changing connections. Conversations and uncertain-request reconciliation belong to their original connection; switching preserves your code, recorded assistance, and retry requirement.

Automatic coaching starts off for a new connection. Model, effort, and automatic-checkpoint preferences are saved separately for each connection. Approach and test-result checkpoints can be enabled separately. Personal automatic checkpoints conserve allowance at 20% remaining. Reconnection reconciles an uncertain request instead of sending it twice. Full conversations and all connection settings remain private on this computer. Pause/Sync transfers learning work between computers, while each uses its own saved connection.

## Finish once, publish deliberately

**Finish** opens one summary. Review the latest test status, recall, assistance, explanation and complexity evidence, and active minutes. The learning question is **What would you recognize or do differently next time?** A brief takeaway is optional; unsupported details remain unrecorded.

- **Again:** the target reasoning could not be reconstructed without help supplying it.
- **Hard:** successful independent recall with substantial effort.
- **Good:** ordinary independent recall.
- **Easy:** fluent independent recall.
- **Unknown:** recall was not established or remains disputed; the scheduling interval stays unchanged.

Correctness, explanation, effort, and assistance remain separate. Speed or a passing check does not establish recall. Material help that supplied missing target reasoning requires Again. A stopped attempt before an initial answer does not automatically become failed recall. Reviewed disagreements remain unknown rather than qualifying as independent success.

**Finish locally** commits the candidate, evidence, reflection, completion receipt, and closed status together. A failed or unfinished attempt is retained too. Only current passing implementation code is promoted to a solution artifact. Retrying a completion returns its original receipt instead of adding another review. Local completion does not wait for coaching, GitHub, exported files, or deletion of an old attempt directory.

**Publish & finish** is the explicit public action after the summary. **Review & publish** on Today previews saved sessions, destination, and files before publication. When several sessions await publication, choose the sessions to publish in the preview. Others can stay local. The selected records supply their own archived code and reflections. A changed batch requires a fresh preview. Publication failure means the session remains saved locally; the next local session is still available.

Publication includes the scoped candidate/solution, reviewed learning evidence, and reflection. It excludes full chats, authentication, runtime logs, and unrelated source files. A shared public-content check also applies to draft synchronization. Rejected text stays local with the affected path identified.

## Repairs between sessions

A repair is one fresh application of a corrected rule. It becomes eligible after at least 24 elapsed hours and affects relevant skills rather than unrelated topics. A conceptual error may need an explanation; a repeated implementation slip can use a small debugging example.

Write the application, save it, and optionally run your assertions. Passing learner-written assertions alone does not establish conceptual correctness. **Check application with Codex** supplies a labeled judgment; review it before confirming success. An external coach's judgment can be recorded when offline. Unknown, failed, or disputed evidence leaves the repair open.

A repair ends with its own saved session. If an older workflow left a paused main problem behind it, that problem resumes on the next Start action. Repair time includes work with the coach and is counted once.

## Synchronization and two computers

Saving and synchronization are separate. Pause saves locally and queues a scoped draft backup. Sync retries requested work. Check the result before changing computers. On the other computer, Start fetches the saved draft and restores the same durable attempt. Multiple saved attempts require an explicit choice; divergent drafts are preserved instead of overwritten.

When GitHub cannot be checked, **Continue locally** uses saved work on this computer. Locally completed sessions and pending publication do not force you to publish before continuing. The synchronization message describes the requested backup or publication; the editor's save indicator describes the current draft.

Git works in a private export checkout. Practice does not switch the source repository's branch or commit its unrelated changes. Existing public review IDs and artifact formats are retained. A successful remote acknowledgment is required before the service reports synchronization success.

## Recovery and storage

The local database is outside the checkout: `%LOCALAPPDATA%\PracticeRoom\workspaces\<workspace-id>\practice.sqlite3` on Windows. Codex owns authentication separately under application data. Linux uses `$XDG_DATA_HOME/PracticeRoom` or `~/.local/share/PracticeRoom`.

The first launch imports legacy `attempt/`, `.practice/`, `.study-local/`, and published learning artifacts. Original files remain untouched. Old grouped completions recover their original IDs and minutes; completed supporting work is not counted again. Unfinished work becomes a single current activity, with other saved work retained for later. Conflicting records remain available in recovery rather than choosing an arbitrary winner.

After import, editing the old repository `attempt/current.py` does not edit the current browser attempt. Use the browser or the revision-checked CLI. An explicitly opened VS Code candidate is a private editor copy; checkpoint/pause/completion imports its edits only when they do not conflict with the saved candidate.

Settings provides restart and private diagnostics. If the local server is unreachable, reopen **Start Study.cmd**, keep the browser draft open, and retry. Download work when a save cannot be confirmed. Database schema upgrades require a verified backup; do not copy an active SQLite file without its transaction state or delete application-data recovery files while work is pending.

## Useful commands

Use the installed interpreter, for example `.venv\Scripts\python.exe -m study <command>`. Outside the checkout, provide `--root <path>` before the command. Browser and terminal commands use the same service and database.

| Task | Command |
|---|---|
| Open the browser app | `study app` |
| Restart the owned app | `study app --restart` |
| Start / resume locally | `study practice --no-sync` |
| Restricted coaching context | `study coach-context` |
| Record the initial answer | `study note reasoning --approach "..."` |
| Open an editor after the answer | Add `--open` to the reasoning command |
| Save a proposed candidate | `study save --file <draft> --session-id <id> --revision <n> --digest <digest>` |
| Record help | `study note assistance --level <minor|guided|substantial> --summary "..."` |
| Check / interrupt code | `study checkpoint --json` / `study stop` |
| Independent assessment to guided | `study guided` |
| Record a reasoning retry | `study retry "..."` |
| Pause / retry synchronization | `study pause` / `study sync` |
| Finish through a summary | `study complete` |
| Finish locally | `study finish --rating <again|hard|good|easy|unknown> --takeaway "..."` |
| Publish saved evidence | `study publish <session-id>` |
| Preserve a divergent draft | `study recover` |
| Extend planned time | `study continue --minutes 10` |
| Review evidence and progress | `study insights` |

Keep the initial independent attempt and assistance record honest. Passing once does not prove retained mastery. Workflow version 4's next 12 one-problem sessions form a separate descriptive baseline; older grouped history remains available and continues to schedule reviews.