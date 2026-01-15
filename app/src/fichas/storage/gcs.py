from __future__ import annotations

import io
from datetime import timedelta
from uuid import uuid4

from fastapi import UploadFile
from google.cloud import storage

from fichas.storage.base import StorageBackend, StorageSaveResult, safe_filename


class GCSStorage(StorageBackend):
    def __init__(self, bucket_name: str):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def save(self, upload: UploadFile) -> StorageSaveResult:
        filename = safe_filename(upload.filename or "arquivo")
        storage_key = f"{uuid4()}_{filename}"
        blob = self.bucket.blob(storage_key)
        upload.file.seek(0)
        blob.upload_from_file(upload.file, content_type=upload.content_type)
        size = blob.size or 0
        content_type = upload.content_type or "application/octet-stream"
        return StorageSaveResult(storage_key=storage_key, filename=filename, content_type=content_type, size=size)

    def open(self, storage_key: str):
        blob = self.bucket.blob(storage_key)
        data = blob.download_as_bytes()
        return io.BytesIO(data)

    def get_download_url(self, storage_key: str, filename: str | None = None) -> str | None:
        blob = self.bucket.blob(storage_key)
        disposition = None
        if filename:
            disposition = f'attachment; filename="{filename}"'
        return blob.generate_signed_url(
            expiration=timedelta(minutes=15),
            method="GET",
            response_disposition=disposition,
        )
