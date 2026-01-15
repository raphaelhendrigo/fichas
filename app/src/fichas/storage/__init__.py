from __future__ import annotations

from fichas.settings import settings
from fichas.storage.base import StorageBackend
from fichas.storage.gcs import GCSStorage
from fichas.storage.local import LocalStorage

_storage: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND.lower() == "gcs":
            if not settings.GCS_BUCKET:
                raise RuntimeError("GCS_BUCKET nao configurado")
            _storage = GCSStorage(settings.GCS_BUCKET)
        else:
            _storage = LocalStorage(settings.LOCAL_STORAGE_PATH)
    return _storage
