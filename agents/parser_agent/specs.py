"""parser_agent specs: no tools, no memory (pure extraction)."""

from pathlib import Path

from agents.core.schemas import ProfileData
from agents.harness import AgentSpec, Budget

PROMPTS = Path(__file__).parent / "prompts"

EXTRACT_SECTION = AgentSpec(
    id="parser.extract_section", agent="parser", prompt=PROMPTS / "extract.md", output=ProfileData,
    description="把简历的一个分区抽取为结构化资料", tier="fast",
    budget=Budget(max_input_tokens=12000, max_iterations=2, max_repairs=1, temperature=0.0),
)
