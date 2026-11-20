from agents.contracts import AgentCard

CARD = AgentCard(name="jd", description="岗位原文结构化", produces=("JobBrief",),
                 specs=("jd.normalize",), allowed_materials=("job_page",))
