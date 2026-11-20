from agents.contracts import AgentCard

CARD = AgentCard(name="resume", description="依据匹配与简历写作", consumes=("JobBrief", "EvidenceClaim"),
                 produces=("ResumeEvidence", "ResumeDraft", "MaterialRequest"),
                 specs=("resume.match", "resume.rewrite_project", "resume.headline", "resume.polish"),
                 allowed_materials=("job_brief", "project", "selected", "confirmed_evidence", "job_detail", "profile_brief"),
                 tools=("get_material", "recall_preferences", "remember_preference", "search_knowledge"),
                 memory_namespaces=("global", "resume"))
