from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MaterialRequestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: dict = Field(default_factory=dict)
    gap_type: str
    question: str
    priority: Literal["low", "medium", "high"] = "medium"
    origin: dict = Field(default_factory=dict)
    status: Literal["proposed", "open", "resolved", "dismissed"] = "proposed"


class ProfileDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    kind: Literal["replace", "add"]
    context: str
    old: str
    new: str


class ProfileUpdateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume_id: int
    version: int
    diffs: list[ProfileDiff] = Field(default_factory=list)
    status: Literal["proposed", "applied", "dismissed"] = "proposed"
