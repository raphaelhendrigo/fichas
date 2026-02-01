from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from fichas.db import SessionLocal
from fichas.models import FichaTemplate, OcrJob, UploadedDocument
from fichas.schemas import normalize_template_schema
from fichas.services.ocr import (
    build_ocr_result,
    detect_file_type,
    extract_text_from_pdf,
    map_fields_to_ficha,
    preprocess_image,
    run_paddle_ocr,
)
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

        extracted_text = ""
        ocr_items: list[dict[str, object]] = []

        if detect_file_type(file_path) == "pdf":
            extracted_text, images = extract_text_from_pdf(file_path)
            if images:
                for image in images[:1]:
                    processed = preprocess_image(image)
                    ocr_items.extend(run_paddle_ocr(processed))
        else:
            from PIL import Image

            image = Image.open(file_path)
            processed = preprocess_image(image)
            ocr_items = run_paddle_ocr(processed)

        if extracted_text and not ocr_items:
            ocr_items = [
                {"text": line, "confidence": 1.0, "bbox": None}
                for line in extracted_text.splitlines()
                if line.strip()
            ]

        extracted_text, ocr_items = build_ocr_result(ocr_items)
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
        job.ocr_raw_json = ocr_items
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
