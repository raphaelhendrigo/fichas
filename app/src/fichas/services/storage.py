from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from fichas.models import UploadedDocument
from fichas.settings import settings

ALLOWED_CONTENT_TYPES = {"application/pdf"}
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}


def _is_allowed(content_type: str | None, filename: str | None) -> bool:
    if content_type:
        if content_type in ALLOWED_CONTENT_TYPES or content_type.startswith("image/"):
            return True
        if content_type not in {"application/octet-stream", "binary/octet-stream"}:
            return False

    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return True
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed:
        return guessed in ALLOWED_CONTENT_TYPES or guessed.startswith("image/")
    return False


def _safe_extension(filename: str | None, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext:
        return ext
    guess = mimetypes.guess_extension(content_type or "")
    return guess or ".bin"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_upload(upload: UploadFile, user_id, db: Session) -> UploadedDocument:
    content_type = (upload.content_type or "").lower()
    if not _is_allowed(content_type, upload.filename):
        raise ValueError("Tipo de arquivo nao permitido.")

    max_bytes = int(settings.MAX_UPLOAD_MB) * 1024 * 1024
    base_dir = Path(settings.OCR_UPLOAD_DIR).resolve()
    _ensure_dir(base_dir)

    original_name = Path(upload.filename or "upload").name
    extension = _safe_extension(original_name, content_type)
    filename = f"{uuid.uuid4().hex}{extension}"
    file_path = (base_dir / filename).resolve()
    if base_dir not in file_path.parents:
        raise ValueError("Caminho de upload invalido.")

    size = 0
    try:
        with file_path.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Arquivo excede o limite permitido.")
                handle.write(chunk)
    except Exception:
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        raise

    document = UploadedDocument(
        user_id=user_id,
        original_filename=original_name,
        content_type=content_type,
        storage_path=filename,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def resolve_upload_path(storage_path: str) -> Path:
    base_dir = Path(settings.OCR_UPLOAD_DIR).resolve()
    file_path = (base_dir / storage_path).resolve()
    if base_dir not in file_path.parents:
        raise ValueError("Caminho de upload invalido.")
    return file_path
