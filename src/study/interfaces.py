"""Validated browser contracts for guided learning and coaching."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPractice(Input):
    minutes: int = Field(default=60, ge=5, le=180)
    include_new: bool = False


class AdvancePractice(Input):
    answer: str = Field(default="", max_length=12000)
    quality: Literal["complete", "partial", "failed", "novel"] = "complete"
    skip: bool = False
    passed: bool = False
    assistance: Literal["none", "minor", "guided", "substantial"] = "none"
    revision: int | None = None


class Revision(Input):
    revision: int


class FinishPractice(Input):
    session_id: str = Field(pattern=r"^[a-zA-Z0-9]{1,64}$")
    rating: Literal["again", "hard", "good", "easy", "unknown"]
    takeaway: str = Field(max_length=12000)
    explained: bool = False
    constraints_met: bool = False
    minutes: float | None = Field(default=None, gt=0, le=1440)
    publish: bool = False
    revision: int
    stopped: bool = False


class RetryReasoning(Revision):
    answer: str = Field(min_length=12, max_length=8000)


class ApplyProposal(Revision):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{8,64}$")
    kind: Literal["code", "evidence"] = "code"


class CoachPreferences(Input):
    automatic: bool = True
    approach: bool = True
    check: bool = True
    model: str | None = None
    effort: str | None = None


class RepairDraft(Input):
    answer: str = Field(max_length=12000)
    revision: int | None = None


class RepairReview(RepairDraft):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{8,64}$")
