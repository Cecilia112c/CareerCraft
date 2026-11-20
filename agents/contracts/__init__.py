"""Typed handoff contracts shared by agents and the deterministic coordinator."""

from agents.contracts.cards import AgentCard
from agents.contracts.job import JobBrief, Requirement
from agents.contracts.meta import ArtifactRef, SourceRef
from agents.contracts.meta import ArtifactMeta
from agents.contracts.evidence import ResumeEvidence, RequirementMatch, EvidenceRef
from agents.contracts.requests import MaterialRequestContract
from agents.contracts.interview import InterviewBrief, Finding

__all__ = ["AgentCard", "JobBrief", "Requirement", "ArtifactRef", "SourceRef", "ArtifactMeta",
           "ResumeEvidence", "RequirementMatch", "EvidenceRef", "MaterialRequestContract", "InterviewBrief", "Finding"]
