"""Fill documents that fell into manual entry during a live-model run.

Uses separate free-tier model buckets when one is quota-limited. Demo only.
Run from api/:  uv run python ../scripts/live_fill.py
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path.cwd()))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.extract.pipeline import process_document
from app.models import Document, DocumentStatus, User

MODELS = ["gemini-3.1-flash-lite", "gemini-3.8-flash"]


def main() -> None:
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == "exec@demo.local"))
        actor_id = actor.id if actor else None
        docs = db.scalars(
            select(Document).where(Document.status == DocumentStatus.NEEDS_MANUAL_ENTRY)
        ).all()
        print(f"manual documents: {len(docs)}", flush=True)

        for index, document in enumerate(docs, start=1):
            for model in MODELS:
                settings.gemini_model = model
                print(
                    f"[{index}/{len(docs)}] {str(document.type):8} "
                    f"{document.file_name[:28]:28} -> {model}",
                    flush=True,
                )
                process_document(db, document.id, actor_id=actor_id)
                db.refresh(document)
                if document.status == DocumentStatus.EXTRACTED:
                    print("    extracted", flush=True)
                    break
                print(f"    manual: {(document.error_detail or '')[:110]}", flush=True)
                document = db.get(Document, document.id)
            time.sleep(5)


if __name__ == "__main__":
    main()
