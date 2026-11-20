from pydantic import BaseModel, ConfigDict, Field


class InterviewBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: dict
    resume_text: str
    history: list[dict] = Field(default_factory=list)
    claimed_coverage: list[dict] = Field(default_factory=list)
    mode: str = "blind"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    req_id: str = ""
    question_id: str = ""
    gap_type: str = ""
    detail: str


class InterviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    review_topics: list[str] = Field(default_factory=list)
    project_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    overall: float = 0.0
    findings: list[Finding] = Field(default_factory=list)
