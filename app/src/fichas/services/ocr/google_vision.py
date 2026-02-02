from __future__ import annotations

import io
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from google.api_core import exceptions as gcp_exceptions
from google.protobuf.json_format import MessageToDict
from PIL import Image, ImageOps

from .provider import OcrResult

logger = logging.getLogger(__name__)

_VISION_CLIENT = None
_STORAGE_CLIENT = None


@dataclass
class WordToken:
    text: str
    confidence: float


def _get_vision_client():
    global _VISION_CLIENT
    if _VISION_CLIENT is None:
        from google.cloud import vision

        _VISION_CLIENT = vision.ImageAnnotatorClient()
    return _VISION_CLIENT


def _get_storage_client():
    global _STORAGE_CLIENT
    if _STORAGE_CLIENT is None:
        from google.cloud import storage

        _STORAGE_CLIENT = storage.Client()
    return _STORAGE_CLIENT


def _maybe_register_heif() -> bool:
    try:
        import pillow_heif  # type: ignore
    except Exception:
        return False
    try:
        pillow_heif.register_heif_opener()
    except Exception:
        return False
    return True


def _normalize_image_bytes(file_bytes: bytes, mime_type: str, filename: str | None) -> tuple[bytes, str]:
    if mime_type in {"image/heic", "image/heif"} or (filename or "").lower().endswith((".heic", ".heif")):
        if not _maybe_register_heif():
            raise ValueError("Arquivo HEIC nao suportado no momento.")

    image = Image.open(io.BytesIO(file_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")

    output = io.BytesIO()
    if mime_type in {"image/jpeg", "image/jpg"}:
        image.save(output, format="JPEG", quality=95, optimize=True)
        return output.getvalue(), "image/jpeg"
    image.save(output, format="PNG")
    return output.getvalue(), "image/png"


def _extract_full_text_from_response(response) -> str:
    if getattr(response, "full_text_annotation", None) and response.full_text_annotation.text:
        return response.full_text_annotation.text
    annotations = getattr(response, "text_annotations", None) or []
    if annotations:
        return annotations[0].description
    return ""


def _extract_full_text_from_dict(payload: dict[str, Any]) -> str:
    full = payload.get("fullTextAnnotation") or {}
    text = full.get("text") or ""
    if text:
        return text
    annotations = payload.get("textAnnotations") or []
    if annotations:
        return annotations[0].get("description", "")
    return ""


def _iter_words_from_full_text(full_text_annotation) -> Iterable[WordToken]:
    for page in getattr(full_text_annotation, "pages", []) or []:
        for block in getattr(page, "blocks", []) or []:
            for paragraph in getattr(block, "paragraphs", []) or []:
                for word in getattr(paragraph, "words", []) or []:
                    text = "".join(symbol.text for symbol in word.symbols)
                    yield WordToken(text=text, confidence=float(word.confidence or 0.0))


def _iter_words_from_full_text_dict(full_text_annotation: dict[str, Any]) -> Iterable[WordToken]:
    for page in full_text_annotation.get("pages", []) or []:
        for block in page.get("blocks", []) or []:
            for paragraph in block.get("paragraphs", []) or []:
                for word in paragraph.get("words", []) or []:
                    symbols = word.get("symbols", []) or []
                    text = "".join(symbol.get("text", "") for symbol in symbols)
                    yield WordToken(text=text, confidence=float(word.get("confidence") or 0.0))


def _normalize_token(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _build_line_items(text: str, words: list[WordToken]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not text:
        return items

    index = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        tokens = [_normalize_token(token) for token in stripped.split() if token.strip()]
        confidences: list[float] = []
        for token in tokens:
            if not token:
                continue
            while index < len(words) and _normalize_token(words[index].text) != token:
                index += 1
            if index < len(words) and _normalize_token(words[index].text) == token:
                confidences.append(words[index].confidence)
                index += 1
        if confidences:
            confidence = sum(confidences) / len(confidences)
        else:
            confidence = 0.4
        items.append({"text": stripped, "confidence": confidence, "bbox": None})
    return items


def _with_retries(label: str, retries: int, func):
    attempt = 0
    while True:
        try:
            return func()
        except gcp_exceptions.GoogleAPICallError as exc:
            attempt += 1
            if attempt > retries:
                logger.error("GCP OCR falhou: %s", label, exc_info=exc)
                raise
            delay = min(2 ** attempt, 8)
            logger.warning("GCP OCR retry %s (%s/%s)", label, attempt, retries)
            time.sleep(delay)


def extract_from_image_bytes(
    file_bytes: bytes,
    mime_type: str,
    filename: str | None,
    *,
    timeout_seconds: int,
    retries: int,
    language_hints: list[str],
) -> OcrResult:
    from google.cloud import vision

    normalized_bytes, normalized_mime = _normalize_image_bytes(file_bytes, mime_type, filename)
    client = _get_vision_client()
    image = vision.Image(content=normalized_bytes)
    context = vision.ImageContext(language_hints=language_hints) if language_hints else None

    def _call():
        return client.document_text_detection(image=image, image_context=context, timeout=timeout_seconds)

    response = _with_retries("image", retries, _call)
    if response.error and response.error.message:
        raise ValueError(response.error.message)

    extracted_text = _extract_full_text_from_response(response).strip()
    words = list(_iter_words_from_full_text(response.full_text_annotation)) if response.full_text_annotation else []
    items = _build_line_items(extracted_text, words)

    raw = {
        "provider": "google_vision",
        "mime_type": normalized_mime,
        "full_text_annotation": MessageToDict(
            response.full_text_annotation._pb, preserving_proto_field_name=True
        )
        if response.full_text_annotation
        else {},
    }
    return OcrResult(text=extracted_text, items=items, raw=raw)


def extract_from_pdf_bytes(
    file_bytes: bytes,
    mime_type: str,
    filename: str | None,
    *,
    bucket: str,
    max_pages: int | None,
    timeout_seconds: int,
    retries: int,
    language_hints: list[str],
) -> OcrResult:
    from google.cloud import vision

    client = _get_vision_client()
    storage_client = _get_storage_client()
    bucket_client = storage_client.bucket(bucket)

    suffix = ".pdf" if mime_type.startswith("application/pdf") else ".tiff"
    object_id = uuid.uuid4().hex
    input_blob_name = f"ocr-input/{object_id}{suffix}"
    output_prefix = f"ocr-output/{object_id}/"
    input_uri = f"gs://{bucket}/{input_blob_name}"
    output_uri = f"gs://{bucket}/{output_prefix}"

    input_blob = bucket_client.blob(input_blob_name)
    input_blob.upload_from_string(file_bytes, content_type=mime_type)

    try:
        gcs_source = vision.GcsSource(uri=input_uri)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)
        gcs_destination = vision.GcsDestination(uri=output_uri)
        output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=20)
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        image_context = vision.ImageContext(language_hints=language_hints) if language_hints else None

        request_kwargs: dict[str, Any] = {
            "input_config": input_config,
            "features": [feature],
            "output_config": output_config,
        }
        if image_context is not None:
            request_kwargs["image_context"] = image_context
        if max_pages:
            max_pages = int(max_pages)
            request_kwargs["pages"] = list(range(1, max_pages + 1))

        async_request = vision.AsyncAnnotateFileRequest(**request_kwargs)

        def _call():
            operation = client.async_batch_annotate_files(requests=[async_request])
            return operation.result(timeout=timeout_seconds)

        _with_retries("pdf", retries, _call)

        responses: list[dict[str, Any]] = []
        for blob in storage_client.list_blobs(bucket, prefix=output_prefix):
            if not blob.name.endswith(".json"):
                continue
            payload = json.loads(blob.download_as_bytes())
            responses.extend(payload.get("responses", []))

        texts: list[str] = []
        items: list[dict[str, Any]] = []
        raw_full_text: list[dict[str, Any]] = []
        for response in responses:
            if response.get("error"):
                logger.warning("OCR PDF page error: %s", response.get("error"))
                continue
            full_text = _extract_full_text_from_dict(response).strip()
            if not full_text:
                continue
            texts.append(full_text)
            full_text_annotation = response.get("fullTextAnnotation") or {}
            words = list(_iter_words_from_full_text_dict(full_text_annotation))
            items.extend(_build_line_items(full_text, words))
            raw_full_text.append(full_text_annotation)

        extracted_text = "\n".join(texts).strip()
        if not extracted_text:
            raise ValueError("OCR nao retornou texto para o PDF.")

        raw = {
            "provider": "google_vision",
            "mime_type": mime_type,
            "pages": raw_full_text,
        }
        return OcrResult(text=extracted_text, items=items, raw=raw)
    finally:
        try:
            input_blob.delete()
        except Exception:
            logger.debug("Falha ao remover OCR input %s", input_blob_name, exc_info=True)
        try:
            for blob in storage_client.list_blobs(bucket, prefix=output_prefix):
                blob.delete()
        except Exception:
            logger.debug("Falha ao remover OCR output %s", output_prefix, exc_info=True)
