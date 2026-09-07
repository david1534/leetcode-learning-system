# Daily practice

## Open and resume

Open **Start Study.cmd** or run `study app`. Today has one Start / Resume action, a time budget, the selection reason, waiting reviews, and synchronization status. In VS Code, Ctrl+Shift+B opens the app. Keep Codex in this repository and say “review my approach” or “help with one issue.” Codex can inspect `study summary` without asking you to copy problem IDs or code.

The default budget is 60 active minutes: up to 10 for retrieval and one repair, about 40 for the main problem, seven for tests and explanation, and three for finishing. These are adjustable defaults. Choose a shorter session when needed. A break is suggested at 45 minutes; reaching a boundary preserves your work. Browser focus never pauses the timer because conversations with Codex count as study. Use the phase menu when switching to explanation or other work. Pause stops the timer. If you leave the timer running, correct total minutes in the completion preview.

Weekdays allow new material. Weekends default to reviews, with an explicit override on Today. When reviews are waiting, every third main opportunity protects eligible new work. Every fifth main opportunity prefers a never-exposed transfer variant. If no full task fits, a short Recall can revisit an approach while the full implementation remains due. Waiting and postponed reviews are shown honestly. Prerequisite anchors and relevant repair gates determine eligibility; unrelated branches can continue.

## Practice without a paperwork ritual

Read the prompt, constraints, signature, and public examples. Record a few sentences: your approach, why it fits, and one correctness condition or important edge case. “I don’t know yet” is a valid initial attempt. Plain language is sufficient. Codex should follow up only on an important missing or incorrect idea.

Before that initial answer, topic labels, revealing links, and candidate code are hidden. For Transfer, avoid opening the repository catalog, reference files, or topic links before committing to your approach. After exposure, the same variant becomes ordinary practice, even if you stopped without solving it.

Write code in the local editor. Save status appears above it; unsaved text is also recoverable from browser storage. Check solution runs public and assessment cases against a fixed copy of your saved code. Public-example failures are shown; hidden-case details are excluded from the coach summary. A timeout or Stop is distinct from an incorrect answer. If the code changes, rerun the check before successful completion.

Hints reveal one step at a time. Retry the code or reasoning before the next hint. Assistance is classified by what it supplied: minor syntax or generic prompting, guided missing reasoning, or substantial algorithm construction. Hint count alone does not set a rating. Record conversational help too.

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

Ready to advance requires independent anchor exercises. Retained requires two qualifying independent implementations at least seven elapsed days apart on every core exercise, plus an unseen transfer pass for the topic. Same-day practice or crossing midnight cannot establish retention. A later lapse changes current readiness for affected prerequisites; it does not erase learning history or block unrelated topics.

## Finish, stop, or pause

Finish asks one learning question: **What would you recognize or do differently next time?** Codex may draft the durable record from your answer and actual session evidence. No invented reflections or mandatory multi-part essay is needed. Check the recall rating, whether the explanation and constraints were established, and the measured minutes. Leave minutes blank to use the live timer, including completion administration.

Finish locally saves the candidate, evidence, and brief reflection. A failed or unfinished attempt is archived too. Only a current passing implementation is promoted to `solutions/`. Cancel leaves the session open. Repeating completion uses the same event ID and does not create another review.

**Publish & finish** is the explicit public action. Review the destination and evidence first: github.com/david1534/leetcode-learning-system. It publishes scoped learning artifacts, never raw chat transcripts. If you finish several sessions offline, the preview shows the number of saved sessions and publishes them together; each keeps its own review ID and archived reflection. A locally finished session can be published later from its completion card or `study publish <session-id>`. `study complete` provides the same workflow in the terminal; type YES, LOCAL, or cancel at the final prompt.

Pause saves locally and attempts to synchronize the scoped draft to its attempt branch. It does not merge the completed history. “Saved locally; sync pending” means you can continue working on this computer. Network failure never discards a completed attempt. Retry sync or keep the pending completion local before starting another task.

## Small, relevant repairs

A conceptual misconception calls for one fresh application of the corrected rule and a brief explanation if needed. A repeated implementation slip usually calls for a small debugging exercise. Codex records stable skill IDs; known historical aliases merge into one skill gate. At least 24 elapsed hours must pass before a delayed repair. A repair affects relevant skills rather than all new work.

Start a repair on Today; its timer includes work with Codex. Closing it pauses and preserves its answer. Record whether the application was checked and what assistance it needed. Independent passes clear the gate. Guided or unsuccessful repairs remain open and their time is counted. Standalone repair records have their own explicit Publish action; repairs during a problem are included in that problem’s publication.

## Recovery and two computers

Pause and sync before moving computers. On the other computer, Start / Resume fetches the saved attempt and resumes the same durable session. Check the synchronization message before assuming that another computer has received your work.

If the app and Codex edit the same code, the older save is rejected. Both texts remain available. Compare them, then choose the saved version or deliberately save your draft. Codex must use `study save --file <draft> --revision <observed-revision> --digest <observed-digest>` for candidate edits. A direct external edit also invalidates the next revision check.

If computers diverge, Git refuses to overwrite a branch. **Preserve divergent draft** (or `study recover`) backs up this computer’s attempt under `.study-local/recovery/` and creates a distinct attempt branch. Both Git versions remain available. Resume the desired version; Git branch selection is an advanced recovery step. Multiple remote attempts require choosing one explicitly. The app never chooses an arbitrary winner or force-pushes.

Sessionless candidate files are preserved. Recover draft archives them under `progress/orphan-drafts/` before a fresh start. A completion receipt allows recovery if the program stops after saving evidence but before closing the active directory.

Local browser drafts, check jobs, repair timers, locks, and publication receipts live in ignored `.study-local/` or browser storage. They are not a replacement for pausing and syncing before moving computers. Do not delete these recovery files while publication is pending.

## Useful coach commands

| Action | Command |
| --- | --- |
| Open the app | `study app` |
| Start / resume offline | `study practice --no-sync` |
| Read the shared state | `study summary` |
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

The first 12 modern main sessions establish a baseline of delayed implementation, unseen transfer, and completion administration. Progress shows counts alongside rates, including separate minor, guided, and substantial help. Median administration of three minutes or less is the initial target. Existing history lacks comparable transfer and repair-time data, so it cannot establish that this release improves learning per hour.
