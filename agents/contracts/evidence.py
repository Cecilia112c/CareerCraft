from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    statement: str
    shared_terms: int = 0


class RequirementMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    req_id: str
    requirement: str
    coverage: Literal["strong", "partial", "none"]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reason: str = ""


class ResumeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: int | None = None
    matches: list[RequirementMatch] = Field(default_factory=list)
    missing_req_ids: list[str] = Field(default_factory=list)
