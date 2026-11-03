from __future__ import annotations

import io
import json
from dataclasses import dataclass

import fitz
from PIL import Image

from .storage import Storage

MAX_EDGE_PX = 2000
RENDER_DPI = 200


@dataclass
class RenderedPage:
    idx: int
    image_key: str
    width: int
    height: int
    words_key: str | None
    source: str
    text: str


def _normalise(words: list[tuple], width: float, height: float) -> list[dict]:
    result = []
    for word in words:
        x0, y0, x1, y1, text = word[0], word[1], word[2], word[3], word[4]
        result.append(
            {
                "t": text,
                "x0": round(x0 / width, 5),
                "y0": round(y0 / height, 5),
                "x1": round(x1 / width, 5),
                "y1": round(y1 / height, 5),
            }
        )
    return result


def render_pdf(data: bytes, prefix: str, storage: Storage) -> list[RenderedPage]:
    pages: list[RenderedPage] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        if document.is_encrypted:
            raise ValueError("encrypted_pdf")
        for index, page in enumerate(document):
            rect = page.rect
            zoom = min(2.6, MAX_EDGE_PX / max(rect.width, rect.height))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=88, optimize=True)
            image_key = f"{prefix}/page-{index + 1}.jpg"
            storage.put(image_key, buffer.getvalue(), "image/jpeg")

            raw_words = page.get_text("words")
            text = page.get_text("text")
            words_key = None
            source = "NONE"
            if raw_words:
                source = "TEXT"
                words_key = f"{prefix}/page-{index + 1}.json"
                payload = {
                    "page": index + 1,
                    "width": round(rect.width, 2),
                    "height": round(rect.height, 2),
                    "text": text,
                    "words": _normalise(raw_words, rect.width, rect.height),
                }
                storage.put(words_key, json.dumps(payload).encode(), "application/json")

            pages.append(
                RenderedPage(
                    idx=index + 1,
                    image_key=image_key,
                    width=image.width,
                    height=image.height,
                    words_key=words_key,
                    source=source,
                    text=text,
                )
            )
    return pages


def page_lines(pages: list[dict]) -> list[dict]:
    """Group words into visual lines, preserving column order by x.

    Each page dict: {idx, words: [{t,x0,y0,x1,y1}]}
    Returns [{page, text}] sorted by page then vertical position.
    """
    lines: list[dict] = []
    for page in pages:
        page_idx = page.get("idx") or page.get("page") or 1
        rows: list[dict] = []
        for word in sorted(page.get("words", []), key=lambda w: (w["y0"], w["x0"])):
            centre = (word["y0"] + word["y1"]) / 2
            for row in rows:
                if abs(row["y"] - centre) < 0.006:
                    row["words"].append(word)
                    break
            else:
                rows.append({"y": centre, "words": [word]})
        for row in sorted(rows, key=lambda r: r["y"]):
            words = sorted(row["words"], key=lambda w: w["x0"])
            text = " ".join(w["t"] for w in words).strip()
            if text:
                lines.append({"page": page_idx, "text": text, "words": words})
    return lines


def bbox_for(pdf: bytes, page_idx: int, needle: str) -> dict | None:
    if not needle:
        return None
    try:
        with fitz.open(stream=pdf, filetype="pdf") as document:
            page = document[page_idx - 1]
            rect = page.rect
            hits = page.search_for(needle)
            if not hits:
                # numeric values may be split by thousands separators; try without them
                hits = page.search_for(needle.replace(",", ""))
            if not hits:
                return None
            box = hits[0]
            return {
                "x0": round(box.x0 / rect.width, 5),
                "y0": round(box.y0 / rect.height, 5),
                "x1": round(box.x1 / rect.width, 5),
                "y1": round(box.y1 / rect.height, 5),
            }
    except Exception:
        return None
