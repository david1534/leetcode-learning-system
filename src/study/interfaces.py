"""Validated browser contracts for guided learning and coaching."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPractice(Input):
    minutes: int = Field(default=60, ge=5, le=180)
    include_new: bool = False
    synchronize: bool = True


class AdvancePractice(Input):
    session_id: str | None = None
    answer: str = Field(default="", max_length=12000)
    quality: Literal["complete", "partial", "failed", "novel", "unknown"] = "unknown"
    skip: bool = False
    passed: bool = False
    assistance: Literal["none", "minor", "guided", "substantial"] = "none"
    revision: int | None = None


class Revision(Input):
    session_id: str | None = None
    revision: int


class FinishPractice(Input):
    session_id: str = Field(pattern=r"^[a-zA-Z0-9]{1,64}$")
    rating: Literal["again", "hard", "good", "easy", "unknown"]
    takeaway: str = Field(default="", max_length=12000)
    explained: bool = False
    constraints_met: bool = False
    minutes: float | None = Field(default=None, gt=0, le=1440)
    publish: bool = False
    revision: int
    stopped: bool = False
    recall_confirmed: bool = False
    expected_session_ids: list[str] | None = None


class RetryReasoning(Revision):
    answer: str = Field(min_length=12, max_length=8000)


class ApplyProposal(Revision):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{8,64}$")
    kind: Literal["code", "evidence"] = "code"


class CoachPreferences(Input):
    automatic: bool = False
    approach: bool = False
    check: bool = False
    model: str | None = None
    effort: str | None = None


class RepairDraft(Input):
    session_id: str | None = None
    answer: str = Field(max_length=12000)
    revision: int | None = None


class RepairReview(RepairDraft):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{8,64}$")


class SaveCode(Revision):
    code: str = Field(max_length=200000)
    code_digest: str | None = None


class Reasoning(Input):
    session_id: str | None = None
    answer: str = Field(min_length=1, max_length=12000)
    quality: Literal["novel", "complete", "partial", "failed", "unknown"] = "unknown"
    revision: int | None = None


class ErrorResponse(BaseModel):
    code: str
    detail: str
    diagnostic_id: str | None = None
    saved_state: Literal["unknown", "confirmed"] = "unknown"


class OptionalRevision(Input):
    session_id: str | None = None
    revision: int | None = None


class Hint(OptionalRevision):
    retried: bool = False


class Phase(OptionalRevision):
    phase: Literal[
        "recall", "implementation", "explanation", "repair", "administration", "learning"
    ]


class Assistance(OptionalRevision):
    level: Literal["minor", "guided", "substantial"]
    summary: str = Field(min_length=1, max_length=12000)
    source: str = "conversation"
    supplied_missing_recall: bool = False


class EvidenceFinding(Input):
    dimension: Literal["recall", "explanation", "constraints", "misconception", "repair"]
    value: Literal["success", "failure", "unknown"]
    evidence: str = Field(default="", max_length=12000)
    explanation: str = Field(default="", max_length=12000)
    source: str | None = None
    recorded_at: str | None = None
    code_digest: str | None = None


class Evidence(OptionalRevision):
    findings: list[EvidenceFinding] = Field(max_length=30)


class Publish(Input):
    session_ids: list[str] | None = None
    session_id: str = Field(pattern=r"^[a-zA-Z0-9]{1,64}$")
    include_saved: bool = False
    expected_session_ids: list[str] | None = None


class Pause(OptionalRevision):
    synchronize: bool = True


class ChooseAttempt(Input):
    branch: str = Field(pattern=r"^attempt/[a-zA-Z0-9._/-]+$", max_length=200)


class Recovery(Input):
    conflict_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9]{1,64}$")
    use_incoming: bool = False


class StartActivity(StartPractice):
    problem_id: str | None = None
    activity: Literal["learn", "recall", "implement", "transfer"] = "implement"
    revision: int | None = None


ACTION_INPUTS = {
    "save": SaveCode,
    "reasoning": Reasoning,
    "finish": FinishPractice,
    "phase": Phase,
    "assistance": Assistance,
    "evidence": Evidence,
    "publish": Publish,
    "pause": Pause,
    "hint": Hint,
    "check": OptionalRevision,
    "worked-example": OptionalRevision,
    "choose-attempt": ChooseAttempt,
    "recover": Recovery,
    "start": StartActivity,
    "sync": Input,
    "stop": Input,
    "keep-local": Input,
    "evaluate": Input,
}


class ContinueFocus(Input):
    minutes: int = Field(ge=1, le=15)


ACTION_INPUTS["continue"] = ContinueFocus


class CheckSolution(OptionalRevision):
    code_digest: str | None = None


ACTION_INPUTS["check"] = CheckSolution
