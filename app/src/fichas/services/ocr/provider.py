from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from typing import Any

from fichas.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str
    items: list[dict[str, Any]]
    raw: dict[str, Any] | None = None


def _normalize_mime_type(mime_type: str | None, filename: str | None) -> str:
    value = (mime_type or "").split(";")[0].strip().lower()
    if value and value not in {"application/octet-stream", "binary/octet-stream"}:
        return value
    guessed, _ = mimetypes.guess_type(filename or "")
    return (guessed or value or "application/octet-stream").lower()


def _is_pdf_like(mime_type: str, filename: str | None) -> bool:
    if mime_type in {"application/pdf", "application/x-pdf"}:
        return True
    if mime_type in {"image/tiff", "image/tif"}:
        return True
    suffix = (filename or "").lower()
    return suffix.endswith(".pdf") or suffix.endswith(".tif") or suffix.endswith(".tiff")


def _parse_language_hints(value: str | None) -> list[str]:
    if not value:
        return []
    hints = [hint.strip() for hint in value.split(",") if hint.strip()]
    return hints


def _get_bucket() -> str | None:
    return settings.GCS_OCR_BUCKET or settings.GCS_BUCKET


def validate_ocr_config(*, require_bucket_for_pdf: bool = False) -> None:
    provider = (settings.GCP_OCR_PROVIDER or "google_vision").strip().lower()
    if provider != "google_vision":
        raise ValueError(f"OCR provider nao suportado: {provider}.")

    if require_bucket_for_pdf and not _get_bucket():
        raise ValueError("GCS_OCR_BUCKET obrigatorio para OCR de PDF/TIFF.")

    if not _get_bucket():
        logger.warning("GCS_OCR_BUCKET nao configurado; OCR de PDF/TIFF ficara desabilitado.")


def ocr_extract(
    file_bytes: bytes,
    mime_type: str | None,
    filename: str | None,
    options: dict[str, Any] | None = None,
) -> OcrResult:
    if not file_bytes:
        raise ValueError("Arquivo vazio.")

    normalized_mime = _normalize_mime_type(mime_type, filename)
    is_pdf = _is_pdf_like(normalized_mime, filename)

    validate_ocr_config(require_bucket_for_pdf=is_pdf)

    bucket = _get_bucket()

    hints = _parse_language_hints(
        (options or {}).get("language_hints")
        or settings.OCR_LANGUAGE_HINTS
        or settings.OCR_LANG
    )
    max_pages = (options or {}).get("max_pages")
    if max_pages is None:
        max_pages = settings.OCR_MAX_PAGES
    if max_pages is not None and int(max_pages) <= 0:
        max_pages = None
    timeout_seconds = (options or {}).get("timeout_seconds")
    if timeout_seconds is None:
        timeout_seconds = settings.OCR_TIMEOUT_SECONDS
    retries = (options or {}).get("retries")
    if retries is None:
        retries = settings.OCR_RETRY

    from . import google_vision

    if is_pdf:
        return google_vision.extract_from_pdf_bytes(
            file_bytes,
            normalized_mime,
            filename,
            bucket=bucket,
            max_pages=max_pages,
            timeout_seconds=timeout_seconds,
            retries=retries,
            language_hints=hints,
        )

    return google_vision.extract_from_image_bytes(
        file_bytes,
        normalized_mime,
        filename,
        timeout_seconds=timeout_seconds,
        retries=retries,
        language_hints=hints,
    )
