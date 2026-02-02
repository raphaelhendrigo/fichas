import io
import os

import pytest
from PIL import Image, ImageDraw

from fichas.services.ocr.provider import ocr_extract
from fichas.settings import settings

RUN_INTEGRATION = os.getenv("RUN_GCP_INTEGRATION_TESTS") == "1"


def _has_credentials() -> bool:
    return bool(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT_ID")
    )


if not RUN_INTEGRATION:
    pytest.skip("GCP integration tests disabled.", allow_module_level=True)

if not _has_credentials():
    pytest.skip("GCP credentials not configured for integration tests.", allow_module_level=True)


def _configure_settings() -> None:
    settings.GCP_OCR_PROVIDER = "google_vision"
    settings.OCR_MAX_PAGES = 1
    if os.getenv("OCR_LANGUAGE_HINTS"):
        settings.OCR_LANGUAGE_HINTS = os.getenv("OCR_LANGUAGE_HINTS")
    if os.getenv("GCS_OCR_BUCKET"):
        settings.GCS_OCR_BUCKET = os.getenv("GCS_OCR_BUCKET")
    if os.getenv("GCS_BUCKET") and not settings.GCS_OCR_BUCKET:
        settings.GCS_BUCKET = os.getenv("GCS_BUCKET")


def _image_bytes() -> bytes:
    image = Image.new("RGB", (1000, 600), "white")
    draw = ImageDraw.Draw(image)
    for offset in range(0, 320, 80):
        draw.text((40, 40 + offset), "TESTE OCR", fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    image = Image.new("RGB", (1000, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 200), "TESTE OCR PDF", fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PDF")
    return buf.getvalue()


def test_google_vision_image_ocr():
    _configure_settings()
    result = ocr_extract(_image_bytes(), "image/png", "test.png")
    assert result.text


def test_google_vision_pdf_ocr():
    bucket = os.getenv("GCS_OCR_BUCKET") or os.getenv("GCS_BUCKET")
    if not bucket:
        pytest.skip("GCS_OCR_BUCKET required for PDF OCR integration test.")

    _configure_settings()
    result = ocr_extract(_pdf_bytes(), "application/pdf", "test.pdf")
    assert result.text
