"""Regenerate the TDD deliverable from TDD.md.

Default output: TDD.pdf (the submission format).
Optional: --docx also writes TDD.docx.

Requires:
    uv pip install --python .venv/bin/python pypandoc-binary weasyprint

Then:
    .venv/bin/python scripts/build_tdd.py
"""
from __future__ import annotations

import argparse
import pathlib
import tempfile

import pypandoc
from weasyprint import HTML

ROOT = pathlib.Path(__file__).resolve().parent.parent
TDD = ROOT / "TDD.md"
CSS = ROOT / "docs" / "tdd-print.css"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", action="store_true", help="also write TDD.docx")
    args = parser.parse_args()

    css = CSS.read_text()
    html = pypandoc.convert_file(str(TDD), "html5", extra_args=["--standalone"])
    html = html.replace("</head>", f"<style>\n{css}\n</style>\n</head>")

    if args.docx:
        pypandoc.convert_file(
            str(TDD),
            "docx",
            outputfile=str(ROOT / "TDD.docx"),
            extra_args=["--toc", "--toc-depth=2"],
        )
        print(f"TDD.docx {pathlib.Path(ROOT / 'TDD.docx').stat().st_size:,} bytes")

    HTML(string=html, base_url=str(ROOT)).write_pdf(str(ROOT / "TDD.pdf"))
    print(f"TDD.pdf  {pathlib.Path(ROOT / 'TDD.pdf').stat().st_size:,} bytes")

    # Intermediate HTML is written outside the repository on purpose.
    debug = pathlib.Path(tempfile.gettempdir()) / "customs-ai-tdd.html"
    debug.write_text(html)


if __name__ == "__main__":
    main()
