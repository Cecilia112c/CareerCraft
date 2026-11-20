"""Turn a normalized JD into an attributable, candidate-independent handoff."""

import hashlib
import re
from difflib import SequenceMatcher

from agents.core.schemas import JobPosting
from agents.contracts.job import JobBrief


def build_brief(job: JobPosting, source_text: str = "") -> dict:
    segments = [part.strip(" -•\t") for part in re.split(r"[\r\n；;。]+", source_text)
                if part.strip(" -•\t")]
    requirements = []
    for ordinal, raw in enumerate(job.requirements, 1):
        statement = raw.strip()
        if not statement:
            continue
        fingerprint = hashlib.sha256(statement.encode()).hexdigest()[:10]
        if source_text and statement in source_text:
            quote = statement
        elif segments:
            def score(segment: str) -> float:
                latin = set(re.findall(r"[a-z][a-z0-9+#.-]+", statement.lower()))
                common = len(latin & set(re.findall(r"[a-z][a-z0-9+#.-]+", segment.lower())))
                similarity = SequenceMatcher(None, statement.lower(), segment.lower()).ratio()
                return common * 0.2 + similarity
            quote = max(segments, key=score)[:240]
        else:
            quote = statement
        requirements.append({"req_id": f"req_{ordinal}_{fingerprint}", "text": statement,
                             "category": "must", "skills": [term for term in job.keywords if term.lower() in statement.lower()],
                             "source_quote": quote})
    return JobBrief.model_validate({"title": job.title, "company": job.company, "city": job.city,
            "requirements": requirements, "responsibilities": list(job.responsibilities),
            "skills": list(job.keywords), "summary": job.summary}).model_dump()
