import pytest

import fichas.services.ocr.google_vision as google_vision
from fichas.services.ocr.provider import OcrResult, ocr_extract, validate_ocr_config
from fichas.settings import settings


def test_ocr_extract_requires_bucket_for_pdf(monkeypatch):
    monkeypatch.setattr(settings, "GCP_OCR_PROVIDER", "google_vision")
    monkeypatch.setattr(settings, "GCS_OCR_BUCKET", None)
    monkeypatch.setattr(settings, "GCS_BUCKET", None)

    with pytest.raises(ValueError):
        ocr_extract(b"data", "application/pdf", "arquivo.pdf")


def test_validate_ocr_config_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "GCP_OCR_PROVIDER", "foo")

    with pytest.raises(ValueError):
        validate_ocr_config()


def test_ocr_extract_image_uses_google(monkeypatch):
    monkeypatch.setattr(settings, "GCP_OCR_PROVIDER", "google_vision")

    def fake_extract(*_args, **_kwargs):
        return OcrResult(
            text="ok",
            items=[{"text": "ok", "confidence": 0.9, "bbox": None}],
            raw={"provider": "google_vision"},
        )

    monkeypatch.setattr(google_vision, "extract_from_image_bytes", fake_extract)

    result = ocr_extract(b"data", "image/png", "arquivo.png")
    assert result.text == "ok"
    assert result.items
