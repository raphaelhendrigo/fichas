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
    ".jpe",
    ".jfif",
    ".pjpeg",
    ".pjp",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".dib",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}

_IMAGE_SIGNATURES = (
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/gif", b"GIF87a"),
    ("image/gif", b"GIF89a"),
    ("image/bmp", b"BM"),
    ("image/tiff", b"II*\x00"),
    ("image/tiff", b"MM\x00*"),
)


def _sniff_image_mime(header: bytes | None) -> str | None:
    if not header:
        return None
    for mime, signature in _IMAGE_SIGNATURES:
        if header.startswith(signature):
            return mime
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return "image/heic"
        if brand in {b"heif", b"heix"}:
            return "image/heif"
    return None


def _is_allowed(content_type: str | None, filename: str | None, header: bytes | None = None) -> bool:
    if content_type:
        if content_type in ALLOWED_CONTENT_TYPES or content_type.startswith("image/"):
            return True
        if content_type not in {"application/octet-stream", "binary/octet-stream"}:
            if header and _sniff_image_mime(header):
                return True
            return False

    if header and _sniff_image_mime(header):
        return True

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
    header = upload.file.read(32)
    upload.file.seek(0)
    sniffed_mime = _sniff_image_mime(header)
    effective_type = content_type
    if sniffed_mime:
        if not effective_type or effective_type in {"application/octet-stream", "binary/octet-stream"}:
            effective_type = sniffed_mime
        elif not effective_type.startswith("image/") and effective_type not in ALLOWED_CONTENT_TYPES:
            effective_type = sniffed_mime

    if not _is_allowed(effective_type, upload.filename, header):
        raise ValueError("Tipo de arquivo nao permitido.")

    max_bytes = int(settings.MAX_UPLOAD_MB) * 1024 * 1024
    base_dir = Path(settings.OCR_UPLOAD_DIR).resolve()
    _ensure_dir(base_dir)

    original_name = Path(upload.filename or "upload").name
    extension = _safe_extension(original_name, effective_type)
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
        content_type=effective_type or content_type,
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
