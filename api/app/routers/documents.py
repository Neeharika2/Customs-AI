from __future__ import annotations

import hashlib
import io
import uuid

from PIL import Image, ImageOps

from fastapi import APIRouter, BackgroundTasks, File, Form, Response, UploadFile
from sqlalchemy import delete, select

from ..config import settings
from ..db import SessionLocal
from ..deps import CurrentUser, DbSession, audit, problem
from ..checks.engine import run_checks
from ..extract.pipeline import _derive_shipment_status, process_document
from ..models import (
    Check,
    Document,
    DocumentStatus,
    DocumentType,
    Field,
    LineItem,
    Page,
    Shipment,
    ShipmentStatus,
)
from ..schemas import DocumentOut, PageOut
from ..services.storage import get_storage

router = APIRouter(prefix="/api", tags=["documents"])

MAGIC = [
    (b"%PDF-", "application/pdf", "pdf"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


def _process(document_id: str, actor_id: str | None = None) -> None:
    with SessionLocal() as db:
        process_document(db, document_id, actor_id=actor_id)


def _document(db, document_id: str, org_id: str) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise problem(404, "document_not_found", "Document not found.")
    shipment = db.get(Shipment, document.shipment_id)
    if not shipment or shipment.org_id != org_id:
        raise problem(404, "document_not_found", "Document not found.")
    return document


@router.post("/shipments/{shipment_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    shipment_id: str,
    background: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    type: DocumentType = Form(...),
    file: UploadFile = File(...),
) -> DocumentOut:
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "shipment_not_found", "Shipment not found.")

    data = await file.read()
    if len(data) == 0:
        raise problem(422, "empty_file", "The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise problem(
            413,
            "file_too_large",
            f"Files must be under {settings.max_upload_mb} MB.",
        )

    detected = None
    for magic, mime, extension in MAGIC:
        if data.startswith(magic):
            detected = (mime, extension)
            break
    if not detected:
        raise problem(415, "unsupported_type", "Upload a PDF, JPEG or PNG.")

    # Photographs and scans arrive as images. Wrap them in a one-page PDF so the
    # renderer and the extraction pipeline have a single input format.
    if detected[0] != "application/pdf":
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "PDF", resolution=150)
        data = buffer.getvalue()
        detected = ("application/pdf", "pdf")

    same_type = db.scalar(
        select(Document).where(Document.shipment_id == shipment_id, Document.type == type)
    )
    if same_type:
        raise problem(
            409,
            "document_type_exists",
            f"This shipment already has a {str(type).lower()} document. Only one of each type is allowed.",
        )

    digest = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(
        select(Document).where(Document.shipment_id == shipment_id, Document.sha256 == digest)
    )
    if duplicate:
        raise problem(
            409,
            "duplicate_document",
            "This file is already attached to the shipment.",
        )

    key = f"org/{user.org_id}/shipment/{shipment_id}/doc-{uuid.uuid4()}.{detected[1]}"
    get_storage().put(key, data, detected[0])

    document = Document(
        shipment_id=shipment_id,
        type=type,
        storage_key=key,
        file_name=file.filename or "document",
        mime_type=detected[0],
        size_bytes=len(data),
        sha256=digest,
        status=DocumentStatus.UPLOADED,
        uploaded_by=user.id,
    )
    db.add(document)
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="document.uploaded",
        entity="document",
        entity_id=document.id,
        meta={"type": str(type)},
    )
    db.commit()
    db.refresh(document)

    background.add_task(_process, document.id, user.id)
    return DocumentOut(
        id=document.id,
        type=document.type,
        file_name=document.file_name,
        page_count=document.page_count,
        status=document.status,
        error_code=document.error_code,
        error_detail=document.error_detail,
        created_at=document.created_at,
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user: CurrentUser, db: DbSession) -> Response:
    document = _document(db, document_id, user.org_id)
    shipment = db.get(Shipment, document.shipment_id)
    if not shipment:
        raise problem(404, "document_not_found", "Document not found.")
    if shipment.status in {
        ShipmentStatus.READY,
        ShipmentStatus.EXPORTED,
        ShipmentStatus.AWAITING_APPROVAL,
    }:
        raise problem(409, "locked", "Reopen or reject the shipment before removing a document.")

    db.execute(delete(Field).where(Field.document_id == document.id))
    db.execute(delete(LineItem).where(LineItem.document_id == document.id))
    db.execute(delete(Check).where(Check.shipment_id == shipment.id))
    db.delete(document)
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="document.deleted",
        entity="document",
        entity_id=document.id,
        meta={"type": str(document.type), "file": document.file_name},
    )
    db.commit()
    run_checks(db, shipment.id)
    _derive_shipment_status(db, shipment.id)
    return Response(status_code=204)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    document_id: str,
    background: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
) -> DocumentOut:
    document = _document(db, document_id, user.org_id)
    shipment = db.get(Shipment, document.shipment_id)
    if not shipment:
        raise problem(404, "document_not_found", "Document not found.")
    if shipment.status in {ShipmentStatus.READY, ShipmentStatus.EXPORTED}:
        raise problem(409, "locked", "Reopen the shipment before re-extracting.")

    document.status = DocumentStatus.UPLOADED
    document.error_code = None
    document.error_detail = None
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="document.reprocess",
        entity="document",
        entity_id=document.id,
        meta={"type": str(document.type)},
    )
    db.commit()
    background.add_task(_process, document.id, user.id)
    return DocumentOut(
        id=document.id,
        type=document.type,
        file_name=document.file_name,
        page_count=document.page_count,
        status=document.status,
        error_code=None,
        error_detail=None,
        created_at=document.created_at,
    )


@router.get("/documents/{document_id}/pages/{idx}", response_model=PageOut)
def page_url(document_id: str, idx: int, user: CurrentUser, db: DbSession) -> PageOut:
    document = _document(db, document_id, user.org_id)
    page = db.scalar(select(Page).where(Page.document_id == document.id, Page.idx == idx))
    if not page:
        raise problem(404, "page_not_found", "Page not found.")
    direct = get_storage().presigned_get(page.image_key)
    return PageOut(
        idx=page.idx,
        url=direct or f"/api/files/{page.image_key}",
        width=page.width_px,
        height=page.height_px,
        source=str(page.source),
    )


@router.get("/files/{key:path}")
def get_file(key: str, user: CurrentUser) -> Response:
    if not key.startswith(f"org/{user.org_id}/"):
        raise problem(404, "file_not_found", "File not found.")
    data = get_storage().get(key)
    if key.endswith(".jpg"):
        media = "image/jpeg"
    elif key.endswith(".png"):
        media = "image/png"
    elif key.endswith(".json"):
        media = "application/json"
    else:
        media = "application/octet-stream"
    return Response(content=data, media_type=media, headers={"Cache-Control": "private, max-age=300"})
