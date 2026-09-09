# Daily practice

## Open and resume

Open **Start Study.cmd** or run `study app`. Today has one Start / Resume action, a time budget, the selection reason, waiting reviews, and synchronization status. In VS Code, Ctrl+Shift+B opens the app. Dark mode is the default; Settings also offers Light and System. Codex can coach in the Practice panel after ChatGPT sign-in. You can also use desktop Codex in this repository: `study coach-context` supplies its restricted context without opening hidden assessment cases. Commands outside the repository need `study --root <path> ...`.

For installation and updates, start with the [README](README.md). Save or pause before updating, preserve unpublished work and local recovery files, then close the old app terminal and relaunch. The [troubleshooting guide](docs/TROUBLESHOOTING.md) covers setup, connection, timer, draft, and synchronization problems.

The default budget is 60 active minutes: up to 10 for retrieval and one repair, about 40 for the main problem, seven for tests and explanation, and three for finishing. These are adjustable defaults. Choose a shorter session when needed. A break is suggested at 45 minutes; reaching a boundary preserves your work. Browser focus never pauses the timer because conversations with Codex count as study. Use the phase menu when switching to explanation or other work. Pause stops the timer. If you leave the timer running, correct total minutes in the completion preview.

The display counts continuously between server updates, including during repairs. Pausing freezes it; resuming continues from the saved total. A sleeping computer or delayed browser may require the display to catch up to the saved time. Review a reported uncertain gap rather than treating it as confirmed study time.

Weekdays allow new material. Weekends default to reviews, with an explicit override on Today. When reviews are waiting, every third main opportunity protects eligible new work. Every fifth main opportunity prefers a never-exposed transfer variant. If no full task fits, a short Recall can revisit an approach while the full implementation remains due. Waiting and postponed reviews are shown honestly. Prerequisite anchors and relevant repair gates determine eligibility; unrelated branches can continue.

Start / Resume restores a whole guided session: supporting retrieval and at most one repair, the main task, and one completion summary. Sessions shorter than 45 minutes omit supporting work when a main task is available. If an eligible repair is the only next step, Start opens that repair before selecting the main task. Unused supporting time remains available to the main activity. Transfer comes first without related warm-up or repair. Completed guided sessions drive rotation; supporting attempts do not inflate the count. An unavailable transfer opportunity stays due until eligible content fits.

## Connect Codex when useful

Select **Connect Codex**, then **Sign in with ChatGPT**. After signing in, refresh the connection. This app has its own managed login; it never copies desktop credentials. It currently validates CLI version 0.153.4. An incompatible or missing CLI, login problem, or lost connection leaves the editor and local completion available. **Stop coach** and **Stop tests** control separate processes.

Windows checks include the installed Codex desktop app and npm launcher, so a missing PATH entry alone does not require reinstalling. **Help connecting Codex** explains installation if a supported version is unavailable. Settings and repair screens show the connection result as well. After an application update, close the old terminal and reopen **Start Study.cmd**.

The allowance display is shared with your other Codex use. Automatic checkpoints pause at 20% remaining; manual questions remain possible. Unknown or exhausted allowance requires a successful refresh before another turn. This integration does not use API billing, buy credits, or redeem resets. OpenAI controls plan allowances and account credits.

In guided practice, one brief checkpoint follows your initial idea and another follows a meaningful check. Coach preferences can disable these for the current session. Feedback does not run on every keystroke. Model and reasoning-effort selection are advanced preferences; leaving them blank uses Codex defaults. Questions persist across refreshes. Reconnect reconciles an uncertain request instead of automatically sending it twice.

Approach and test-result checkpoints can be disabled separately in Coach preferences.

## Practice without a paperwork ritual

Read the prompt, constraints, signature, and public examples. Record a few sentences: your approach, why it fits, and one correctness condition or important edge case. “I don’t know yet” is a valid initial attempt. Plain language is sufficient. Codex should follow up only on an important missing or incorrect idea.

Before that initial answer, topic labels, revealing links, and candidate code are hidden. For Transfer, avoid opening the repository catalog, reference files, or topic links before committing to your approach. After exposure, the same variant becomes ordinary practice, even if you stopped without solving it.

Write code in the local editor. Save status appears above it; unsaved text is also recoverable from browser storage when available. **Run tests** checks public and assessment cases against a fixed copy of your saved code. Public-example failures are shown; hidden-case details are excluded from the coach summary. A timeout or **Stop tests** is distinct from an incorrect answer. If the code changes, rerun the check before successful completion.

On smaller screens, use the Problem, Code, and Coach tabs available at that width. Arrow keys move between tabs; Home and End select the first and last. Hiding the coach or widening the window restores an available panel. **Ctrl+Enter** (or **Command+Enter** on macOS) follows the same availability rules as **Send**. You can draft your next message while an earlier acknowledgement is pending without losing the new text.

During an independent assessment, choose **Continue independently** or **Switch to guided practice** before conceptual help. Switching freezes your pre-help code and evidence, then continues with your draft. The original assessment remains ended for help; a successful continuation cannot become an unseen transfer pass. Procedural clarification and neutral acknowledgements do not imply missing recall.

Hints reveal one step at a time. Save a fresh reasoning retry or change your code before another hint. Assistance is classified by what it supplied: minor syntax or generic prompting, guided missing reasoning, or substantial algorithm construction. Hint count alone does not set a rating. A proposed code change counts as help when shown; applying it requires **Apply this change** and a new test run. Desktop coaching follows the same conversion and revision rules.

If the concept is unfamiliar and you stall, choose **study a worked example** or ask Codex for one. This changes the activity to Learn and records substantial help. Trace the example, explain a step, then try a faded example or a fresh implementation. Your own candidate is preserved.

## Four activities and clear ratings

| Activity | What it measures |
| --- | --- |
| Learn | Exposure and assisted understanding; does not reschedule implementation |
| Recall | Reconstructing the outline; does not reschedule implementation |
| Implement | Coding and debugging from a blank editor |
| Transfer | First-exposure selection and application on an unfamiliar problem |

Again means the target reasoning could not be reconstructed without help supplying missing reasoning. Hard means successful independent recall with substantial effort. Good means ordinary effort. Easy means fluent independent recall. Correctness, explanation, time/space assessment, and assistance remain separate fields. Faster typing or fewer tests do not determine the recall rating. A generic prompt does not automatically imply algorithmic help.

FSRS remains pinned at 6.3.2, retention 0.9, without coding-specific parameter fitting. New evidence records this configuration. Historical review IDs, ratings, correction records, and solutions are retained; missing legacy evidence stays unknown.

When recall has not been established or remains disputed, it stays unknown and the scheduling interval does not change. Stopping before recording an approach does not automatically mean failed recall.

Ready to advance requires independent anchor exercises. Retained requires two qualifying independent implementations at least seven elapsed days apart on every core exercise, plus an unseen transfer pass for the topic. Same-day practice or crossing midnight cannot establish retention. A later lapse changes current readiness for affected prerequisites; it does not erase learning history or block unrelated topics.

## Finish, stop, or pause

Finish asks one learning question: **What would you recognize or do differently next time?** Codex may draft the durable record from your answer and actual session evidence. No invented reflections or mandatory multi-part essay is needed. Check the recall rating, whether the explanation and constraints were established, and the measured minutes. Leave minutes blank to use the live timer, including completion administration.

Finish locally saves the candidate, evidence, and brief reflection. A failed or unfinished attempt is archived too. Only a current passing implementation is promoted to `solutions/`. Cancel restores the previous stage and retains the reflection draft. Repeating completion uses the same event ID and does not create another review. Coach findings are drafts: review them once, leave unsupported evidence unknown, and mark disagreements as disputed. A disputed explanation or complexity finding cannot silently qualify as an independent pass.

**Publish & finish** is the explicit public action. Review the destination and evidence first: github.com/david1534/leetcode-learning-system. It publishes scoped learning artifacts, never raw chat transcripts. If you finish several sessions offline, the preview shows the number of saved sessions and publishes them together; each keeps its own review ID and archived reflection. A locally finished session can be published later from its completion card or `study publish <session-id>`. `study complete` provides the same workflow in the terminal; type YES, LOCAL, or cancel at the final prompt.

Pause saves locally and attempts to synchronize the scoped draft to its attempt branch. It does not merge the completed history. “Saved locally; sync pending” means you can continue working on this computer. Network failure never discards a completed attempt. Retry sync or keep the pending completion local before starting another task.

## Small, relevant repairs

A conceptual misconception calls for one fresh application of the corrected rule and a brief explanation if needed. A repeated implementation slip usually calls for a small debugging exercise. Codex records stable skill IDs; known historical aliases merge into one skill gate. At least 24 elapsed hours must pass before a delayed repair. A repair affects relevant skills rather than all new work.

An eligible repair can be a supporting stage. Its timer includes Codex work. For a small coding repair, write a fresh example with assertions and use **Run repair assertions**; Stop and the ten-second limit preserve the draft. These learner-authored checks do not by themselves prove the corrected rule. **Check application with Codex** produces a labeled judgment of the fresh application. Review it before confirming success. An unknown or failed coach judgment leaves the repair open. You can record an external coach’s assessment when offline. Continuing resumes the main activity and shared timer; skipping preserves the draft. Supporting repairs belong to the guided session’s single publication.

## Recovery and two computers

Pause and sync before moving computers. On the other computer, Start / Resume fetches the saved attempt and resumes the same durable session. Check the synchronization message before assuming that another computer has received your work.

The scoped pause snapshot includes the parent session, repair draft, supporting artifacts, and pre-help code. It excludes conversations and authentication. Approved learning summaries supply coaching memory across computers after synchronization; full conversations remain local. Timer checkpoints count active work without observing browser focus. Restart or a long sleep gap pauses the timer and marks uncertain time for correction in the completion summary.

If the app and Codex edit the same code, the older save is rejected. Both texts remain available. Compare them, then choose the saved version or deliberately save your draft. Codex must use `study save --file <draft> --revision <observed-revision> --digest <observed-digest>` for candidate edits. A direct external edit also invalidates the next revision check.

The conflict controls are **Other saved version**, **Use other saved version**, **Keep my browser draft**, and **Export my draft**. If an action is slow or times out, refresh the connection and inspect its result before repeating it; a missing acknowledgement does not prove it was rejected. Local saves and browser-only drafts are different from a confirmed remote synchronization. Keep a browser-only draft open or export it before changing browser, port, or computer.

If computers diverge, Git refuses to overwrite a branch. **Preserve divergent draft** (or `study recover`) backs up this computer’s attempt under `.study-local/recovery/` and creates a distinct attempt branch. Both Git versions remain available. Resume the desired version; Git branch selection is an advanced recovery step. Multiple remote attempts require choosing one explicitly. The app never chooses an arbitrary winner or force-pushes.

Sessionless candidate files are preserved. Recover draft archives them under `progress/orphan-drafts/` before a fresh start. A completion receipt allows recovery if the program stops after saving evidence but before closing the active directory.

Local browser drafts, check jobs, repair timers, locks, and publication receipts live in ignored `.study-local/` or browser storage. They are not a replacement for pausing and syncing before moving computers. Do not delete these recovery files while publication is pending.

## Useful coach commands

| Action | Command |
| --- | --- |
| Open the app | `study app` |
| Start / resume offline | `study practice --no-sync` |
| Read the shared state | `study summary` |
| Read restricted coaching context | `study coach-context` |
| Switch an assessment to guided practice | `study guided` |
| Save a reasoning retry | `study retry "..."` |
| Continue or skip supporting work | `study advance --answer "..."` / `study advance --skip` |
| Record a compact answer | `study note reasoning --approach "..." --quality complete` |
| Record help | `study note assistance --level minor --summary "..."` |
| Check / stop code | `study checkpoint --json` / `study stop` |
| Change timing phase | `study phase explanation` |
| Study a worked solution | `study learn-example` |
| Finish with prompts | `study complete` |
| Finish locally | `study finish --rating good --takeaway "..." --explained --constraints-met` |
| Preserve an unsuccessful attempt | `study finish --rating again --stopped --takeaway "..."` |
| Publish saved evidence | `study publish <session-id>` |
| Pause / retry sync | `study pause` / `study sync` |
| Report progress | `study insights --json` |

The next 12 completed guided sessions in workflow version 3 establish a separate baseline of delayed implementation, unseen transfer (including attempts ended for help), and completion administration. Progress shows counts alongside rates, assistance levels, coaching interruptions, response latency, and help escalation. Coaching response time is part of study time, not extra time added again. Median administration of three minutes or less is the initial target. These descriptive results cannot establish a causal learning improvement, and the older history lacks a comparable transfer baseline.
