"""All tables. JSON columns are always re-assigned (never mutated in place)."""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(default=dict):
    return Field(default_factory=default, sa_column=Column(JSON))


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_now)


class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True, foreign_key="user.id")
    data: dict = _json()
    updated_at: datetime = Field(default_factory=_now)


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    filename: str
    path: str
    text: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_now)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    source_url: str = Field(default="", index=True)
    title: str = ""
    company: str = ""
    city: str = ""
    salary: str = ""
    published_text: str = ""
    published_at: Optional[date] = None
    score: int = 0
    data: dict = _json()               # ScoredJob
    is_target: bool = False
    pushed_date: Optional[date] = None
    created_at: datetime = Field(default_factory=_now)
    site: str = ""
    origin: str = "paste"
    detail_level: str = "full"
    status: str = "saved"
    status_history: list = _json(list)
    notes: str = Field(default="", sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=_now)
    brief_artifact_id: str = ""
    raw_sha256: str = ""


class Todo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    title: str
    kind: str = "interview"
    due_at: datetime
    done: bool = False
    created_at: datetime = Field(default_factory=_now)


class InsightSnapshot(SQLModel, table=True):
    """市场技能需求样本（搜索摘要聚合结果），每日推送时刷新一次。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    kind: str = "market"
    query: dict = _json()               # {titles, cities, sources}
    data: dict = _json()                # Insight.as_dict() + samples
    created_at: datetime = Field(default_factory=_now)


class PushSetting(SQLModel, table=True):
    """求职偏好 + 每日推送设置（一人一行）。"""
    user_id: int = Field(primary_key=True, foreign_key="user.id")
    enabled: bool = False
    titles: list = _json(list)          # 目标岗位
    cities: list = _json(list)          # 期望工作地点
    sources: list = _json(lambda: ["boss", "tencent", "bytedance", "alibaba", "huawei", "shixiseng"])
    salary_min: int = 0                 # 期望月薪下限（K），0 = 不限
    salary_max: int = 0                 # 期望月薪上限（K），0 = 不限
    top_n: int = 10                     # 每天推送几个
    push_time: str = "09:00"
    last_push_date: Optional[date] = None


class Resume(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    job_id: Optional[int] = None
    title: str = ""
    current_version: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    artifact_id: str = ""


class ResumeVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    resume_id: int = Field(index=True, foreign_key="resume.id")
    version: int
    data: dict = _json()               # ResumeDoc
    note: str = ""
    evidence_artifact_id: str = ""
    created_at: datetime = Field(default_factory=_now)


class Interview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    job_id: Optional[int] = None
    title: str = ""
    source_label: str = ""
    resume_text: str = Field(default="", sa_column=Column(Text))
    gap_report: dict = _json()
    questions: list = _json(list)
    turns: list = _json(list)
    state: dict = _json()              # {index, follow_count, current}
    report: dict = _json()
    status: str = "preparing"          # preparing / ongoing / answered_all / finished / failed
    created_at: datetime = Field(default_factory=_now)
    source_type: str = ""
    source_id: Optional[int] = None
    source_version: Optional[int] = None
    round: int = 1
    previous_interview_id: Optional[int] = None
    mode: str = "blind"
    brief_artifact_id: str = ""


class Task(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int = Field(index=True)
    kind: str
    status: str = "pending"            # pending / running / done / failed
    progress: int = 0
    stage: str = ""
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Artifact(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    kind: str = Field(index=True)
    schema_version: str = "1"
    version: int = 1
    subject: dict = _json()
    produced_by: dict = _json()
    inputs: list = _json(list)
    sources: list = _json(list)
    status: str = "active"
    content_hash: str = ""
    body: dict = _json()
    created_at: datetime = Field(default_factory=_now)


class WorkflowRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    kind: str
    subject: dict = _json()
    status: str = "running"
    started_at: datetime = Field(default_factory=_now)
    finished_at: Optional[datetime] = None


class WorkflowStep(SQLModel, table=True):
    id: str = Field(primary_key=True)
    run_id: str = Field(index=True, foreign_key="workflowrun.id")
    ordinal: int = 0
    name: str
    node_type: str = "agent"
    status: str = "pending"
    input_summary: str = ""
    output_summary: str = ""
    input_refs: list = _json(list)
    output_refs: list = _json(list)
    agent_run_ids: list = _json(list)
    error: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class KnowledgeSource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    kind: str
    title: str
    filename: str = ""
    path: str = ""
    size: int = 0
    sha256: str = ""
    status: str = "ready"
    error: str = ""
    linked_project_ids: list = _json(list)
    meta: dict = _json()
    created_at: datetime = Field(default_factory=_now)


class KnowledgeChunk(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(index=True, foreign_key="knowledgesource.id")
    user_id: int = Field(index=True, foreign_key="user.id")
    ord: int
    text: str = Field(default="", sa_column=Column(Text))
    meta: dict = _json()


class EvidenceClaim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    statement: str = Field(default="", sa_column=Column(Text))
    claim_type: str = "other"
    project_id: str = ""
    source_chunk_ids: list = _json(list)
    source_quote: str = Field(default="", sa_column=Column(Text))
    status: str = "proposed"
    level: str = "L2"
    origin: str = "extracted"
    confidence: float = 0.0
    confirmed_at: Optional[datetime] = None


class MaterialRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    target: dict = _json()
    gap_type: str = "other"
    question: str = Field(default="", sa_column=Column(Text))
    priority: str = "medium"
    origin: dict = _json()
    status: str = "proposed"
    resolution: dict = _json()
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ResumePatchFeedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    resume_id: int = Field(index=True, foreign_key="resume.id")
    patch_id: str = ""
    reason: str
    created_at: datetime = Field(default_factory=_now)
