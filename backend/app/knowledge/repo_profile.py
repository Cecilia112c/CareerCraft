"""Deterministic overview of the source files accepted from a project ZIP."""

import re
import json
from collections import Counter

LANGUAGES = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".vue": "Vue",
             ".java": "Java", ".go": "Go", ".md": "Markdown"}


def profile_from_text(extracted: str) -> dict:
    headers = list(re.finditer(r"(?m)^## ([^\n]+)\n", extracted))
    sections = [(match.group(1).strip(), extracted[match.end():next_match.start() if next_match else len(extracted)])
                for match, next_match in zip(headers, headers[1:] + [None])]
    files = []
    languages = Counter()
    frameworks = set()
    dependencies = set()
    readme = ""
    for path, content in sections:
        files.append(path)
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if suffix in LANGUAGES:
            languages[LANGUAGES[suffix]] += sum(bool(line.strip()) for line in content.splitlines())
        basename = path.rsplit("/", 1)[-1].lower()
        if basename.startswith("readme"):
            readme = content.strip()[:1200]
        elif basename == "requirements.txt":
            dependencies.update(re.findall(r"(?m)^([A-Za-z][A-Za-z0-9_.-]+)\s*(?:[=<>!~]|$)", content))
        elif basename == "package.json":
            try:
                package = json.loads(content)
                dependencies.update((package.get("dependencies") or {}).keys())
                dependencies.update((package.get("devDependencies") or {}).keys())
            except (ValueError, TypeError):
                pass
        elif basename == "go.mod":
            dependencies.update(re.findall(r"(?m)^\s*([\w.-]+/[\w./-]+)\s+v\d", content))
    lower = extracted.lower()
    for name in ("fastapi", "vue", "react", "django", "flask", "sqlmodel", "spring", "pytest"):
        if re.search(r"\b" + name + r"\b", lower):
            frameworks.add(name)
    modules = sorted({path.split("/")[0] for path in files if "/" in path})[:30]
    return {"file_count": len(files), "languages": dict(languages), "frameworks": sorted(frameworks),
            "dependencies": sorted(dependencies)[:100], "modules": modules, "readme_summary": readme,
            "directory_tree": files[:100], "has_tests": any("test" in path.lower() for path in files),
            "has_ci": any(".github/workflows/" in path or ".gitlab-ci" in path for path in files)}
