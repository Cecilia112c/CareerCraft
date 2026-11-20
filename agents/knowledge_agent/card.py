from agents.contracts import AgentCard

CARD = AgentCard(name="knowledge", description="材料事实抽取", produces=("EvidenceClaim",),
                 specs=("knowledge.extract_claims",), allowed_materials=("knowledge_chunk",))
