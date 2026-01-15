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

app.include_router(web_router)
app.include_router(api_router, prefix="/api/v1")

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def startup_init() -> None:
    if settings.STORAGE_BACKEND.lower() == "local":
        get_storage_backend()
