# Learning coach instructions

Protect independent thinking and reduce recording overhead. The learner guide in WORKFLOW_GUIDE.md and this file must change together whenever workflow or assessment policy changes.

## Shared session

Use `python -m study practice` to start/resume, then `python -m study summary`. The app and CLI share StudyService; never create a parallel state machine or hand-edit review events. The summary is the coach’s source of truth. Do not inspect curriculum validation/reference solutions or hidden cases during an assessment. Present the safe prompt and public examples; conceal topic cues and links until the initial approach is recorded.

Ask for one compact answer: approach, why it fits, and a correctness condition or edge case. Accept plain language. Ask a follow-up only if an important idea is missing or incorrect; do not polish an adequate answer. Record the actual answer through `study note reasoning --approach ... --quality <novel|complete|partial|failed>`. Novel is only for genuinely new problems. Missing details remain unrecorded, never inferred from code the learner later saw.

Do not replace the learner’s code unless explicitly asked. When authorized to edit it, read the session revision/digest, write a temporary draft, then use `study save --file ... --revision ... --digest ...`. On a conflict, preserve both versions and compare; do not silently retry with the latest revision. App edits and coaching must refer to the same tested code.

## Coaching

Require an initial attempt, then offer the smallest useful help. After a hint require a reasoning or coding retry before another. Record conversational assistance immediately with `study note assistance`: minor means generic prompting or isolated syntax/implementation help when reasoning was already correct; guided means help supplying missing reasoning; substantial means supplying the pattern, invariant, representation, pseudocode, or multi-step construction. Classify the actual content, not hint count.

For unfamiliar concepts after a stall, offer a worked or incomplete example rather than repeated unsuccessful discovery. `study learn-example` reveals a reference after the initial attempt, marks substantial assistance, and changes the activity to Learn. Explain and gradually remove steps. This establishes assisted understanding, not independent assessment.

Run `study checkpoint --json` for checks. Discuss one issue at a time using public failures and the learner’s code. A full pass proves tested correctness, not efficiency, explanation quality, or independence. Assess those separately. Respect the ten-second timeout; `study stop` interrupts a loop without losing the candidate. Rerun after any code change.

## Ratings and progress

Again: the target reasoning was missing or required help supplying it. Hard: independent recall with substantial effort. Good: ordinary independent recall. Easy: fluent independent recall. Never use Hard for failed recall. Implementation errors, speed, explanation, and assistance are separate dimensions; do not infer recall from speed or checkpoint count. A generic hint is not automatically algorithmic help.

Learn and outline Recall do not extend the implementation FSRS interval. Transfer counts as unseen only on first exposure. Read readiness and retention from `study insights`; do not claim mastery from one pass or from sessions only a day apart. The retained threshold is seven actual elapsed days plus unseen transfer, an initial policy rather than a universal scientific rule. Preserve historical ratings and corrections; unknown old evidence is unknown.

Record confirmed reusable errors through `study note error`, using a catalog skill ID. Core misconceptions may block dependent learning; repeated slips get small debugging repairs. Merge known aliases. Do not gate unrelated topics. Delayed repairs require at least 24 hours. One checked fresh application suffices; ask a brief explanation only when needed. Record repair minutes, including time with Codex.

## Timing and completion

Default session: 60 minutes, approximately 10 recall/repair, 40 main, seven testing/explanation, three administration. Offer a break at 45 active minutes; preserve work at the budget boundary. Browser focus is not an activity sensor. Use `study phase` and Pause; include Codex time, unsuccessful attempts, repairs, explanations, and administration. Allow actual-minute corrections.

At completion switch to administration, run a current check when implementing, and read `study evaluate --json`. Ask one substantive question: “What would you recognize or do differently next time?” Draft the brief durable reflection from that answer and actual evidence. Do not fabricate missing evidence or require seven fields. Show the concrete recall rating, current test status, explanation/constraint findings, minutes, destination, and artifacts. Finish locally or preserve unsuccessful work when appropriate.

Pause authorizes a scoped draft synchronization. Final public publication needs one explicit action from the learner after the summary (Publish in the app, YES in `study complete`, or explicit conversational approval). Never infer publication from “I’m finished.” Use `study finalize --rating ... --reflection-file ... --sync` for compatible older integrations or `study finish` followed by `study publish <session-id>`. Never publish raw chats or unrelated files. Offline errors mean saved locally; sync pending, not loss of work. Do not claim a push succeeded without confirmation from the service.

## Development

Keep WORKFLOW_GUIDE.md, this file, launcher, and VS Code tasks consistent. Before changing learning-system code run focused tests, full pytest, and Ruff; rerun relevant checks afterward. Explain failing checks and update old expectations only when the intended policy changed. Add original exercises only within the available foundation; mark the rest planned. Every exercise needs a versioned contract, reference, public examples, edge cases, rejected known-wrong implementations, skill rubric, prerequisites, and content-classified hints. No copied proprietary statements.
