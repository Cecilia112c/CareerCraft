from pydantic import BaseModel, ConfigDict, Field


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    req_id: str
    text: str
    category: str = "must"
    skills: list[str] = Field(default_factory=list)
    source_quote: str = ""


class JobBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = ""
    company: str = ""
    city: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    summary: str = ""
