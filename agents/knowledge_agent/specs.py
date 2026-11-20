from pathlib import Path

from pydantic import BaseModel, Field

from agents.harness import AgentSpec, Budget, ContextContract


class CandidateClaim(BaseModel):
    statement: str
    claim_type: str = "other"
    quote: str = ""


class ClaimsOutput(BaseModel):
    claims: list[CandidateClaim] = Field(default_factory=list)


EXTRACT = AgentSpec(
    id="knowledge.extract_claims", agent="knowledge",
    prompt=Path(__file__).parent / "prompts" / "extract_claims.md", output=ClaimsOutput,
    description="从一段用户材料中提取待确认事实", tier="fast",
    budget=Budget(max_input_tokens=8000, max_iterations=2, max_repairs=1, temperature=0),
    context_contract=ContextContract(allowed_materials=("knowledge_chunk",), max_input_tokens=8000),
)
