from agents.contracts import AgentCard

CARD = AgentCard(name="interview", description="独立简历诊断与模拟面试", consumes=("InterviewBrief",),
                 produces=("InterviewReport", "MaterialRequest"),
                 specs=("interview.diagnose", "interview.questions", "interview.evaluate", "interview.report"),
                 memory_namespaces=("interview",))
