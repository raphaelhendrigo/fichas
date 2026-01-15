from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from fichas.storage.base import StorageBackend, StorageSaveResult, safe_filename


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, upload: UploadFile) -> StorageSaveResult:
        filename = safe_filename(upload.filename or "arquivo")
        storage_key = f"{uuid4()}_{filename}"
        destination = self.base_path / storage_key

        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)

        size = destination.stat().st_size
        content_type = upload.content_type or "application/octet-stream"
        return StorageSaveResult(storage_key=storage_key, filename=filename, content_type=content_type, size=size)

    def open(self, storage_key: str):
        return (self.base_path / storage_key).open("rb")

    def get_path(self, storage_key: str) -> Path:
        return self.base_path / storage_key
