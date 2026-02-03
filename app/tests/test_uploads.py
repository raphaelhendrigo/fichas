import io

import pytest
from starlette.datastructures import Headers, UploadFile

from fichas.auth import get_password_hash
from fichas.models import User
from fichas.services.storage import save_upload
from fichas.settings import settings


def _make_upload(content: bytes, content_type: str, filename: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_save_upload_rejects_invalid_type(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)

    user = User(email="upload@test.com", hashed_password=get_password_hash("secret"), is_admin=False)
    db_session.add(user)
    db_session.commit()

    upload = _make_upload(b"data", "text/plain", "teste.txt")
    with pytest.raises(ValueError):
        save_upload(upload, user.id, db_session)


def test_save_upload_enforces_size(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)

    user = User(email="upload2@test.com", hashed_password=get_password_hash("secret"), is_admin=False)
    db_session.add(user)
    db_session.commit()

    upload = _make_upload(b"1", "application/pdf", "arquivo.pdf")
    with pytest.raises(ValueError):
        save_upload(upload, user.id, db_session)


def test_save_upload_accepts_octet_stream_image(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)

    user = User(email="upload3@test.com", hashed_password=get_password_hash("secret"), is_admin=False)
    db_session.add(user)
    db_session.commit()

    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 16
    upload = _make_upload(jpeg_bytes, "application/octet-stream", "camera")
    document = save_upload(upload, user.id, db_session)

    assert document.content_type == "image/jpeg"
    assert document.storage_path.endswith(".jpg")
