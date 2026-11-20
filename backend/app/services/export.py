"""HTML / PDF export. PDF runs Playwright in a subprocess (robust on Windows + uvicorn)."""

from __future__ import annotations

import subprocess
import sys
import uuid

from agents.core.schemas import ResumeDoc
from agents.resume_agent import render_html
from backend.app.config import EXPORT_DIR, ROOT


class ExportError(RuntimeError):
    pass


def export_html(doc: ResumeDoc) -> bytes:
    return render_html(doc, interactive=False).encode("utf-8")


def export_pdf(doc: ResumeDoc) -> bytes:
    stem = EXPORT_DIR / uuid.uuid4().hex
    html_path, pdf_path = stem.with_suffix(".html"), stem.with_suffix(".pdf")
    html_path.write_bytes(export_html(doc))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "backend.app.services.pdf_worker", str(html_path), str(pdf_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=90,
        )
        if proc.returncode != 0 or not pdf_path.exists():
            raise ExportError(
                "PDF 导出失败。请先执行 `python -m playwright install chromium`；"
                "也可以下载 HTML 后用浏览器“打印 → 另存为 PDF”。\n" + (proc.stderr or "")[-300:])
        return pdf_path.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise ExportError("PDF 导出超时") from exc
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
