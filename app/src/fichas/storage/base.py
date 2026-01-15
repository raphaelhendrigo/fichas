from __future__ import annotations

import re
from dataclasses import dataclass
from typing import BinaryIO

from fastapi import UploadFile


@dataclass
class StorageSaveResult:
    storage_key: str
    filename: str
    content_type: str
    size: int


def safe_filename(filename: str) -> str:
    filename = filename or "file"
    filename = filename.strip().replace(" ", "_")
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return filename


class StorageBackend:
    def save(self, upload: UploadFile) -> StorageSaveResult:  # pragma: no cover - interface
        raise NotImplementedError

    def open(self, storage_key: str) -> BinaryIO:  # pragma: no cover - interface
        raise NotImplementedError

    def get_download_url(self, storage_key: str, filename: str | None = None) -> str | None:
        return None
