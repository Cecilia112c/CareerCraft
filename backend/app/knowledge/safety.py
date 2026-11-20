"""Text redaction and bounded chunking for untrusted uploads."""

import re
import io
import zipfile
from pathlib import PurePosixPath

SECRETS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?im)^\s*[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|PASSWORD)\s*=\s*\S+"),
]


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in SECRETS:
        text, found = pattern.subn("[REDACTED]", text)
        count += found
    return text, count


def chunk_text(text: str, size: int = 400, overlap: int = 50) -> list[str]:
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def read_zip_text(data: bytes) -> str:
    """Read bounded source files; reject traversal, links and decompression bombs."""
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("ZIP 超过 20MB")
    parts = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 3000:
            raise ValueError("ZIP 文件数量超过限制")
        for entry in entries:
            path = PurePosixPath(entry.filename.replace("\\", "/"))
            if (path.is_absolute() or entry.filename.startswith(("/", "\\")) or
                    re.match(r"^[A-Za-z]:", entry.filename) or ".." in path.parts or
                    (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("ZIP 包含不安全路径或符号链接")
            if entry.is_dir():
                continue
            total += entry.file_size
            if total > 100 * 1024 * 1024 or entry.file_size > 2 * 1024 * 1024:
                raise ValueError("ZIP 解压后超过限制")
            if any(p in {"node_modules", ".git", "dist", "build", "venv", ".venv"} for p in path.parts):
                continue
            if path.name.startswith(".env") or path.suffix.lower() not in {".py", ".js", ".ts", ".vue", ".md", ".txt", ".json", ".yaml", ".yml", ".java", ".go"}:
                continue
            if path.name.endswith("-lock.json") or path.name in {"package-lock.json", "yarn.lock"}:
                continue
            content = archive.read(entry)
            if b"\x00" in content:
                continue
            parts.append(f"\n## {path}\n" + content.decode("utf-8", errors="replace")[:50000])
    return "\n".join(parts)[:500000]
