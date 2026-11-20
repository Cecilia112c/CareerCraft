"""jd_agent specs. JD pages are untrusted data; no tools, no memory."""

from pathlib import Path

from pydantic import BaseModel, Field

from agents.core.schemas import Str, StrList
from agents.harness import AgentSpec, Budget, ContextContract

PROMPTS = Path(__file__).parent / "prompts"


class JobExtract(BaseModel):
    is_job_page: bool = True
    title: Str = ""
    company: Str = ""
    city: Str = ""
    salary: Str = ""
    experience: Str = ""
    education: Str = ""
    published_text: Str = ""
    responsibilities: StrList = Field(default_factory=list)
    requirements: StrList = Field(default_factory=list)
    keywords: StrList = Field(default_factory=list)
    summary: Str = ""


NORMALIZE = AgentSpec(
    id="jd.normalize", agent="jd", prompt=PROMPTS / "normalize.md", output=JobExtract,
    description="把岗位页面/粘贴的 JD 结构化", tier="fast",
    budget=Budget(max_input_tokens=6000, max_iterations=2, max_repairs=1, temperature=0.0),
    context_contract=ContextContract(allowed_materials=("job_page",), allowed_variables=("hit_title", "hit_url"),
                                     forbidden=("profile", "knowledge", "memory", "resume"),
                                     max_input_tokens=6000),
)
