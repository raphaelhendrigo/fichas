from __future__ import annotations

import mimetypes
from datetime import datetime

from sqlalchemy import select

from fichas.db import SessionLocal
from fichas.models import FichaTemplate, OcrJob, UploadedDocument
from fichas.schemas import normalize_template_schema
from fichas.services.ocr import map_fields_to_ficha
from fichas.services.ocr.provider import ocr_extract
from fichas.services.storage import resolve_upload_path


def process_ocr_job(job_id: str) -> None:
    db = SessionLocal()
    job = None
    try:
        job = db.execute(select(OcrJob).where(OcrJob.id == job_id)).scalar_one_or_none()
        if not job:
            return
        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)

        document = db.execute(select(UploadedDocument).where(UploadedDocument.id == job.document_id)).scalar_one()
        file_path = resolve_upload_path(document.storage_path)

        with file_path.open("rb") as handle:
            file_bytes = handle.read()

        mime_type = (document.content_type or "").lower()
        if not mime_type or mime_type in {"application/octet-stream", "binary/octet-stream"}:
            guessed, _ = mimetypes.guess_type(document.original_filename or file_path.name)
            if guessed:
                mime_type = guessed

        ocr_result = ocr_extract(file_bytes, mime_type, document.original_filename)
        extracted_text = ocr_result.text
        ocr_items = ocr_result.items
        if extracted_text and len(extracted_text) > 30000:
            extracted_text = extracted_text[:30000]

        template_schema = None
        if job.template_id:
            template = db.execute(select(FichaTemplate).where(FichaTemplate.id == job.template_id)).scalar_one_or_none()
            if template:
                template_schema = normalize_template_schema(template.schema_json)

        suggestions = map_fields_to_ficha(extracted_text, ocr_items, template_schema)

        job.status = "done"
        job.extracted_text = extracted_text
        job.ocr_raw_json = {
            "provider": "google_vision",
            "items": ocr_items,
            "raw": ocr_result.raw or {},
        }
        job.field_suggestions_json = suggestions
        job.finished_at = datetime.utcnow()
        db.add(job)
        db.commit()
    except Exception as exc:
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            db.add(job)
            db.commit()
        raise
    finally:
        db.close()
