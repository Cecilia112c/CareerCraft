"""PDF layout extraction and heading-based section splitting (no LLM)."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field


@dataclass
class Line:
    text: str
    size: float = 10.0
    bold: bool = False
    page: int = 1


@dataclass
class Section:
    type: str            # basic | education | experience | projects | skills | awards | summary | other
    title: str
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


SECTION_RULES: list[tuple[str, str]] = [
    ("education", r"教育(经历|背景|信息|经验)?|学历(背景)?|education"),
    ("experience", r"(实习|工作|职业|实践)(经历|经验)|任职经历|实习|internships?|work ?experience|experience"),
    ("projects", r"(项目|科研|研究)(经历|经验|实践|成果)?|projects?|research"),
    ("skills", r"(专业|个人|技术)?技能(特长|清单)?|技术栈|专业能力|skills?"),
    ("awards", r"(获奖|荣誉|奖项|证书)(情况|经历|奖励)?|荣誉奖项|获奖经历|awards?|honors?|certificates?"),
    ("summary", r"自我评价|个人(总结|简介|优势|评价)|关于我|summary|about ?me|profile"),
    ("other", r"校园经历|社团(经历)?|活动经历|学生工作|其他|语言能力|兴趣爱好"),
]
_HEADING_CLEAN = re.compile(r"[\s:：|｜·•●■◆▌▍【】\[\]（）()/]")


def extract_lines(pdf_bytes: bytes) -> list[Line]:
    import fitz  # PyMuPDF

    lines: list[Line] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, start=1):
            data = page.get_text("dict", sort=True)
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for raw in block.get("lines", []):
                    spans = [s for s in raw.get("spans", []) if s.get("text", "").strip()]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in raw["spans"]).strip()
                    text = re.sub(r"\s{2,}", "  ", text)
                    size = max(float(s.get("size", 10)) for s in spans)
                    bold = any((int(s.get("flags", 0)) & 16) or "bold" in str(s.get("font", "")).lower()
                               for s in spans)
                    lines.append(Line(text=text, size=size, bold=bold, page=page_no))
    return lines


def lines_from_text(text: str) -> list[Line]:
    """For pasted text (no font info)."""
    return [Line(text=t.strip()) for t in text.splitlines() if t.strip()]


def classify_heading(line: Line, body_size: float) -> str | None:
    clean = _HEADING_CLEAN.sub("", line.text)
    if not clean or len(clean) > 14:
        return None
    for kind, pattern in SECTION_RULES:
        if re.fullmatch(f"(?:{pattern})", clean, re.I):
            return kind
    if (line.bold and line.size >= body_size * 1.25 and len(clean) <= 8
            and not re.search(r"\d", clean)):
        return "other"
    return None


def split_sections(lines: list[Line]) -> list[Section]:
    if not lines:
        return []
    body_size = statistics.median(line.size for line in lines)
    sections = [Section(type="basic", title="基本信息")]
    for line in lines:
        kind = classify_heading(line, body_size)
        if kind:
            sections.append(Section(type=kind, title=line.text.strip(" :：")))
        else:
            sections[-1].lines.append(line)
    return [s for s in sections if s.lines or s.type != "basic"]
