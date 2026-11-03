"""Vertex AI adapter.

Enabled when GOOGLE_CLOUD_PROJECT and VERTEX_MODEL are set. In local development the
fixture extractor is used instead, and the UI shows a "demo extractor" label so nobody
is misled about what produced the values.
"""
from __future__ import annotations

import json
from decimal import Decimal

from ..config import settings


def is_configured() -> bool:
    return bool(settings.google_cloud_project and settings.vertex_model)


def extract(prompt: str, images: list[bytes], schema: dict) -> tuple[dict, dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.vertex_location,
    )
    parts = [types.Part.from_bytes(data=image, mime_type="image/jpeg") for image in images]
    parts.append(types.Part.from_text(text=prompt))
    response = client.models.generate_content(
        model=settings.vertex_model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    meta = {
        "tokens_in": getattr(usage, "prompt_token_count", 0) or 0,
        "tokens_out": getattr(usage, "candidates_token_count", 0) or 0,
        "model_id": settings.vertex_model,
    }
    text = response.text or "{}"
    return json.loads(text), meta
