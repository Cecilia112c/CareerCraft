"""python -m backend.app.services.pdf_worker <in.html> <out.pdf>"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(html_path: str, pdf_path: str) -> None:
    html = Path(html_path).read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
