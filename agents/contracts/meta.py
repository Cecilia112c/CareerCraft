from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int
    content_hash: str = ""


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    id: str = ""
    quote: str = ""
    url: str = ""


class ArtifactMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    kind: str
    schema_version: str = "1"
    version: int
    subject: dict
    owner_user_id: int
    produced_by: dict
    inputs: list[ArtifactRef] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    status: Literal["draft", "active", "stale", "superseded", "rejected"] = "active"
    content_hash: str
    created_at: datetime
