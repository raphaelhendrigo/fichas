from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fichas.routes.api import router as api_router
from fichas.routes.web import router as web_router
from fichas.settings import settings
from fichas.storage import get_storage_backend
from fichas.services.ocr.provider import validate_ocr_config


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)


setup_logging()

app = FastAPI(title="Fichas TCM-SP", version="0.1.0")

base_path = settings.APP_BASE_PATH
app.include_router(web_router, prefix=base_path)
api_prefix = f"{base_path}/api/v1" if base_path else "/api/v1"
app.include_router(api_router, prefix=api_prefix)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    static_prefix = f"{base_path}/static" if base_path else "/static"
    app.mount(static_prefix, StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def startup_init() -> None:
    if settings.STORAGE_BACKEND.lower() == "local":
        get_storage_backend()
    try:
        validate_ocr_config(require_bucket_for_pdf=False)
    except ValueError as exc:
        logging.getLogger(__name__).error("OCR config invalida: %s", exc)
        raise RuntimeError(str(exc))
