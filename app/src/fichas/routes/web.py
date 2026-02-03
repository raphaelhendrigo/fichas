from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from fichas import __version__
from fichas.auth import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    create_session_token,
    get_current_user_optional,
)
from fichas.db import get_db
from fichas.models import Attachment, Ficha, FichaTemplate, OcrJob, Process, UploadedDocument
from fichas.schemas import (
    FichaBaseForm,
    LoginForm,
    ProcessForm,
    TemplateForm,
    TemplateSchema,
    build_template_field_map,
    normalize_template_schema,
    validation_errors_to_dict,
)
from fichas.services.fichas_service import (
    create_ficha,
    delete_ficha,
    get_ficha,
    list_fichas,
    parse_extras,
    update_ficha,
)
from fichas.services.processos_service import create_process, get_process, list_processes, update_process
from fichas.services.templates_service import (
    create_template,
    create_template_version,
    get_template,
    import_template_payload,
    list_templates,
    set_template_active,
)
from fichas.services.queue import enqueue_process_ocr
from fichas.services.storage import resolve_upload_path, save_upload
from fichas.settings import settings
from fichas.storage import get_storage_backend

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _select_upload(form: Any) -> StarletteUploadFile | None:
    def has_content(upload: Any) -> bool:
        if not isinstance(upload, StarletteUploadFile):
            return False
        if (upload.filename or "").strip():
            return True
        content_type = (upload.content_type or "").lower()
        if content_type and content_type not in {"application/octet-stream", "binary/octet-stream"}:
            return True
        try:
            header = upload.file.read(1)
            upload.file.seek(0)
        except Exception:
            return False
        return bool(header)

    upload_file = form.get("upload_file") if form else None
    camera_file = form.get("camera_file") if form else None
    if has_content(upload_file):
        return upload_file
    if has_content(camera_file):
        return camera_file
    return None


def format_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d")


def format_datetime(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M")


def build_query(params, **overrides):
    data = dict(params)
    data.update({k: v for k, v in overrides.items() if v is not None})
    clean = {k: v for k, v in data.items() if v not in ("", None)}
    return urlencode(clean, doseq=True)


def process_label(process: Process | None):
    if not process:
        return ""
    if process.process_key:
        return process.process_key
    if process.tc_numero and process.ano:
        return f"{process.tc_numero}/{process.ano}"
    return str(process.id)


templates.env.filters["format_date"] = format_date
templates.env.filters["format_datetime"] = format_datetime
templates.env.globals["build_query"] = build_query
templates.env.globals["process_label"] = process_label
templates.env.globals["app_version"] = __version__
templates.env.globals["app_prefix"] = settings.APP_BASE_PATH


def with_prefix(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    if not settings.APP_BASE_PATH:
        return path
    return f"{settings.APP_BASE_PATH}{path}"


templates.env.globals["url_path"] = with_prefix


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def ensure_user(request: Request, db: Session, admin: bool = False):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(with_prefix("/login"), status_code=303)
    if admin and not user.is_admin:
        return RedirectResponse(with_prefix("/"), status_code=303)
    return user


def build_pagination(page: int, page_size: int, total: int) -> dict[str, int | bool]:
    pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size + 1 if total else 0
    end = min(page * page_size, total) if total else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
        "start": start,
        "end": end,
    }


def get_ocr_job(db: Session, job_id: str, user) -> OcrJob | None:
    return (
        db.execute(select(OcrJob).where(OcrJob.id == job_id, OcrJob.user_id == user.id))
        .scalar_one_or_none()
    )


def get_or_create_manual_template(db: Session, user) -> FichaTemplate:
    template = db.execute(select(FichaTemplate).where(FichaTemplate.nome == "Cadastro manual")).scalar_one_or_none()
    if template:
        return template
    schema = {"sections": [{"id": "geral", "label": "Geral", "order": 1, "fields": []}]}
    return create_template(db, "Cadastro manual", "Ficha sem campos extras", schema, user)


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user:
        return RedirectResponse(with_prefix("/"), status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "show_nav": False})


@router.post("/login")
async def login_action(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = LoginForm.model_validate(form)
    user = authenticate_user(db, data.email, data.password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Credenciais invalidas", "show_nav": False},
            status_code=401,
        )

    token = create_session_token(user.id)
    response = RedirectResponse(with_prefix("/"), status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_EXPIRES_SECONDS,
    )
    return response


@router.post("/logout")
def logout_action():
    response = RedirectResponse(with_prefix("/login"), status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    processos_total = db.execute(select(func.count()).select_from(Process)).scalar_one()
    fichas_total = db.execute(select(func.count()).select_from(Ficha)).scalar_one()
    templates_total = db.execute(select(func.count()).select_from(FichaTemplate)).scalar_one()
    active_templates = (
        db.execute(
            select(FichaTemplate)
            .where(FichaTemplate.is_active.is_(True))
            .order_by(FichaTemplate.nome.asc(), FichaTemplate.versao.desc())
            .limit(6)
        )
        .scalars()
        .all()
    )
    recent_fichas = (
        db.execute(
            select(Ficha)
            .options(selectinload(Ficha.process), selectinload(Ficha.template))
            .order_by(Ficha.created_at.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "processos_total": processos_total,
            "fichas_total": fichas_total,
            "templates_total": templates_total,
            "active_templates": active_templates,
            "recent_fichas": recent_fichas,
        },
    )


@router.get("/saiba-mais")
def saiba_mais(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "saiba_mais.html",
        {"request": request, "user": user},
    )


@router.get("/processos")
def processos_list(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    page = int(request.query_params.get("page", "1"))
    page_size = int(request.query_params.get("page_size", settings.PAGINATION_PAGE_SIZE))
    filters = {
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
    }
    processos, total = list_processes(db, filters, page, page_size)
    pagination = build_pagination(page, page_size, total)
    template_name = "partials/processos_table.html" if is_htmx(request) else "processos_list.html"
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "user": user,
            "processos": processos,
            "filters": filters,
            "pagination": pagination,
        },
    )


@router.get("/processos/novo")
def processo_novo(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "processo_form.html",
        {"request": request, "user": user, "processo": None, "form": {}},
    )


@router.post("/processos/novo")
async def processo_criar(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    form_data = dict(form)
    try:
        data = ProcessForm.model_validate(form_data)
    except ValidationError as exc:
        errors = validation_errors_to_dict(exc)
        return templates.TemplateResponse(
            "processo_form.html",
            {"request": request, "user": user, "processo": None, "form": form_data, "errors": errors},
            status_code=400,
        )

    processo = create_process(db, data.model_dump(), user)
    return RedirectResponse(with_prefix(f"/processos/{processo.id}"), status_code=303)


@router.get("/processos/{process_id}")
def processo_detail(process_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    processo = get_process(db, process_id)
    if not processo:
        return RedirectResponse(with_prefix("/processos"), status_code=303)
    return templates.TemplateResponse(
        "processo_detail.html",
        {"request": request, "user": user, "processo": processo},
    )


@router.get("/processos/{process_id}/editar")
def processo_editar(process_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    processo = get_process(db, process_id)
    if not processo:
        return RedirectResponse(with_prefix("/processos"), status_code=303)
    return templates.TemplateResponse(
        "processo_form.html",
        {"request": request, "user": user, "processo": processo, "form": {}},
    )


@router.post("/processos/{process_id}/editar")
async def processo_atualizar(process_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    processo = get_process(db, process_id)
    if not processo:
        return RedirectResponse(with_prefix("/processos"), status_code=303)

    form = await request.form()
    form_data = dict(form)
    try:
        data = ProcessForm.model_validate(form_data)
    except ValidationError as exc:
        errors = validation_errors_to_dict(exc)
        return templates.TemplateResponse(
            "processo_form.html",
            {"request": request, "user": user, "processo": processo, "form": form_data, "errors": errors},
            status_code=400,
        )

    processo = update_process(db, processo, data.model_dump(), user)
    return RedirectResponse(with_prefix(f"/processos/{processo.id}"), status_code=303)


@router.get("/fichas")
def fichas_list(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    page = int(request.query_params.get("page", "1"))
    page_size = int(request.query_params.get("page_size", settings.PAGINATION_PAGE_SIZE))
    data_inicio_raw = request.query_params.get("data_inicio")
    data_fim_raw = request.query_params.get("data_fim")
    filters = {
        "q": request.query_params.get("q"),
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
        "indexador": request.query_params.get("indexador"),
        "template_id": request.query_params.get("template_id"),
        "status": request.query_params.get("status"),
        "data_inicio": None,
        "data_fim": None,
    }
    if data_inicio_raw:
        try:
            filters["data_inicio"] = date.fromisoformat(data_inicio_raw)
        except ValueError:
            pass
    if data_fim_raw:
        try:
            filters["data_fim"] = date.fromisoformat(data_fim_raw)
        except ValueError:
            pass
    fichas, total = list_fichas(db, filters, page, page_size)
    pagination = build_pagination(page, page_size, total)
    templates_list = list_templates(db)
    template_name = "partials/fichas_table.html" if is_htmx(request) else "fichas_list.html"
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "user": user,
            "fichas": fichas,
            "filters": filters,
            "pagination": pagination,
            "templates_list": templates_list,
        },
    )


@router.get("/fichas/importar")
def fichas_importar(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    templates_list = list_templates(db, active_only=True)
    return templates.TemplateResponse(
        "fichas_importar.html",
        {
            "request": request,
            "user": user,
            "templates_list": templates_list,
            "error": None,
        },
    )


@router.post("/fichas/importar")
async def fichas_importar_submit(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    template_id = str(form.get("template_id") or "").strip() or None
    upload = _select_upload(form)
    templates_list = list_templates(db, active_only=True)

    template = get_template(db, template_id) if template_id else None
    if template_id and not template:
        return templates.TemplateResponse(
            "fichas_importar.html",
            {
                "request": request,
                "user": user,
                "templates_list": templates_list,
                "error": "Template invalido.",
            },
            status_code=400,
        )

    if not isinstance(upload, StarletteUploadFile):
        return templates.TemplateResponse(
            "fichas_importar.html",
            {
                "request": request,
                "user": user,
                "templates_list": templates_list,
                "error": "Envie um arquivo para importacao.",
            },
            status_code=400,
        )

    try:
        document = save_upload(upload, user.id, db)
    except ValueError as exc:
        return templates.TemplateResponse(
            "fichas_importar.html",
            {
                "request": request,
                "user": user,
                "templates_list": templates_list,
                "error": str(exc),
            },
            status_code=400,
        )

    job = OcrJob(
        user_id=user.id,
        template_id=template.id if template else None,
        document_id=document.id,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_process_ocr(str(job.id))
    return RedirectResponse(with_prefix(f"/fichas/importar/{job.id}"), status_code=303)


@router.get("/fichas/importar/{job_id}")
def fichas_importar_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return RedirectResponse(with_prefix("/"), status_code=303)
    return templates.TemplateResponse(
        "fichas_importar_status.html",
        {"request": request, "user": user, "job": job},
    )


@router.get("/fichas/importar/{job_id}/status")
def fichas_importar_status_poll(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return Response(status_code=404)
    if job.status == "processing" and job.started_at:
        timeout = int(settings.OCR_TIMEOUT_SECONDS) + 120
        if datetime.now(timezone.utc) - job.started_at > timedelta(seconds=timeout):
            job.status = "failed"
            job.error_message = "OCR expirou ou foi interrompido. Reenvie o arquivo."
            job.finished_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
    if job.status == "done":
        return Response(status_code=200, headers={"HX-Redirect": with_prefix(f"/fichas/importar/{job.id}/revisar")})
    if job.status == "failed":
        return templates.TemplateResponse(
            "partials/ocr_status.html",
            {"request": request, "job": job, "state": "failed"},
        )
    return templates.TemplateResponse(
        "partials/ocr_status.html",
        {"request": request, "job": job, "state": "processing"},
    )


@router.get("/fichas/importar/{job_id}/revisar")
def fichas_importar_revisar(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return RedirectResponse(with_prefix("/"), status_code=303)
    if job.status != "done":
        return RedirectResponse(with_prefix(f"/fichas/importar/{job.id}"), status_code=303)

    template_id = request.query_params.get("template_id") or (str(job.template_id) if job.template_id else None)
    template = get_template(db, template_id) if template_id else None
    templates_list = list_templates(db, active_only=True)
    template_schema = normalize_template_schema(template.schema_json) if template else None

    process_id = request.query_params.get("process_id")
    processo = get_process(db, process_id) if process_id else None

    suggestions = job.field_suggestions_json or {"base": {}, "extras": {}}
    return templates.TemplateResponse(
        "fichas_importar_revisar.html",
        {
            "request": request,
            "user": user,
            "job": job,
            "document": db.execute(select(UploadedDocument).where(UploadedDocument.id == job.document_id)).scalar_one(),
            "template": template,
            "templates_list": templates_list,
            "template_schema": template_schema,
            "processo": processo,
            "base_suggestions": suggestions.get("base", {}),
            "extras_suggestions": suggestions.get("extras", {}),
            "form": {},
            "errors": {},
        },
    )


@router.get("/fichas/importar/{job_id}/processos")
def fichas_importar_processos(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return Response(status_code=404)

    page = int(request.query_params.get("page", "1"))
    page_size = int(request.query_params.get("page_size", 6))
    filters = {
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
    }
    processos, total = list_processes(db, filters, page, page_size)
    pagination = build_pagination(page, page_size, total)
    return templates.TemplateResponse(
        "partials/import_processos_table.html",
        {
            "request": request,
            "job": job,
            "processos": processos,
            "pagination": pagination,
            "template_id": request.query_params.get("template_id"),
        },
    )


@router.get("/fichas/importar/{job_id}/arquivo")
def fichas_importar_arquivo(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return RedirectResponse(with_prefix("/"), status_code=303)
    document = db.execute(select(UploadedDocument).where(UploadedDocument.id == job.document_id)).scalar_one()
    file_path = resolve_upload_path(document.storage_path)
    return FileResponse(file_path, media_type=document.content_type, filename=document.original_filename)


@router.post("/fichas/importar/{job_id}/confirmar")
async def fichas_importar_confirmar(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    job = get_ocr_job(db, job_id, user)
    if not job:
        return RedirectResponse(with_prefix("/"), status_code=303)
    if job.status != "done":
        return RedirectResponse(with_prefix(f"/fichas/importar/{job.id}"), status_code=303)

    form = await request.form()
    form_data = dict(form)
    template_id = form_data.get("template_id") or (str(job.template_id) if job.template_id else None)
    template = get_template(db, template_id) if template_id else None
    templates_list = list_templates(db, active_only=True)
    template_schema = normalize_template_schema(template.schema_json) if template else None

    process_id = form_data.get("process_id")
    processo = get_process(db, process_id) if process_id else None
    if process_id and not processo:
        errors["process_id"] = "Processo invalido"

    suggestions = job.field_suggestions_json or {"base": {}, "extras": {}}
    errors: dict[str, str] = {}

    status_value = str(form_data.get("status") or "ativo").strip().lower()
    if status_value not in {"ativo", "rascunho", "arquivado"}:
        errors["status"] = "Status invalido"
    if not template:
        errors["template_id"] = "Template invalido"

    base_fields = None
    try:
        base_fields = FichaBaseForm.model_validate(form_data)
    except ValidationError as exc:
        errors.update(validation_errors_to_dict(exc))

    extras_json: dict[str, Any] = {}
    if template_schema:
        extras_json, extra_errors = parse_extras(form_data, template_schema)
        for key, value in extra_errors.items():
            errors[f"extra__{key}"] = value

    if errors:
        return templates.TemplateResponse(
            "fichas_importar_revisar.html",
            {
                "request": request,
                "user": user,
                "job": job,
                "document": db.execute(select(UploadedDocument).where(UploadedDocument.id == job.document_id)).scalar_one(),
                "template": template,
                "templates_list": templates_list,
                "template_schema": template_schema,
                "processo": processo,
                "base_suggestions": suggestions.get("base", {}),
                "extras_suggestions": suggestions.get("extras", {}),
                "form": form_data,
                "errors": errors,
            },
            status_code=400,
        )

    if not processo:
        processo = create_process(db, base_fields.model_dump(), user)

    ficha = create_ficha(
        db,
        processo,
        template,
        base_fields.model_dump(),
        extras_json,
        form_data.get("indexador"),
        form_data.get("observacoes"),
        status_value,
        user,
    )
    return RedirectResponse(with_prefix(f"/fichas/{ficha.id}"), status_code=303)


@router.get("/fichas/nova")
def ficha_nova(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    process_id = request.query_params.get("process_id")
    template_id = request.query_params.get("template_id")
    manual = request.query_params.get("manual") == "1" and not process_id
    processo = get_process(db, process_id) if process_id else None
    template = get_template(db, template_id) if template_id else None
    if manual and not template_id:
        template = get_or_create_manual_template(db, user)
    templates_list = list_templates(db, active_only=True)

    process_filters = {
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
    }
    processos = []
    if not manual and not processo:
        processos, _ = list_processes(db, process_filters, 1, 20)

    template_schema = normalize_template_schema(template.schema_json) if template else None
    return templates.TemplateResponse(
        "ficha_form.html",
        {
            "request": request,
            "user": user,
            "manual": manual,
            "processo": processo,
            "template": template,
            "template_schema": template_schema,
            "templates_list": templates_list,
            "processos": processos,
            "process_filters": process_filters,
            "form": {},
            "errors": {},
        },
    )


@router.post("/fichas/nova")
async def ficha_criar(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    form = await request.form()
    form_data = dict(form)
    process_id = form_data.get("process_id")
    template_id = form_data.get("template_id") or request.query_params.get("template_id")
    manual = form_data.get("manual") == "1"
    processo = get_process(db, process_id) if process_id else None
    template = get_template(db, template_id) if template_id else None
    if manual and not template_id:
        template = get_or_create_manual_template(db, user)
    templates_list = list_templates(db, active_only=True)

    errors: dict[str, str] = {}
    status_value = str(form_data.get("status") or "ativo").strip().lower()
    if status_value not in {"ativo", "rascunho", "arquivado"}:
        errors["status"] = "Status invalido"
    if not processo and not manual:
        errors["process_id"] = "Processo invalido"
    if not template:
        errors["template_id"] = "Template invalido"

    base_fields = None
    try:
        base_fields = FichaBaseForm.model_validate(form_data)
    except ValidationError as exc:
        errors.update(validation_errors_to_dict(exc))

    extras_json: dict[str, Any] = {}
    template_schema: TemplateSchema | None = None
    if template and template.schema_json:
        template_schema = normalize_template_schema(template.schema_json)
        extras_json, extra_errors = parse_extras(form_data, template_schema)
        for key, value in extra_errors.items():
            errors[f"extra__{key}"] = value

    if errors:
        return templates.TemplateResponse(
            "ficha_form.html",
            {
                "request": request,
                "user": user,
                "manual": manual,
                "processo": processo,
                "template": template,
                "template_schema": template_schema,
                "templates_list": templates_list,
                "processos": [],
                "process_filters": {},
                "form": form_data,
                "extras": extras_json,
                "errors": errors,
            },
            status_code=400,
        )

    if not processo:
        processo = create_process(db, base_fields.model_dump(), user)

    ficha = create_ficha(
        db,
        processo,
        template,
        base_fields.model_dump(),
        extras_json,
        form_data.get("indexador"),
        form_data.get("observacoes"),
        status_value,
        user,
    )
    return RedirectResponse(with_prefix(f"/fichas/{ficha.id}"), status_code=303)


@router.get("/fichas/{ficha_id}")
def ficha_detail(ficha_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    ficha = get_ficha(db, ficha_id)
    if not ficha:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)
    template_schema = normalize_template_schema(ficha.template.schema_json)
    extras_map = build_template_field_map(template_schema)
    return templates.TemplateResponse(
        "ficha_detail.html",
        {"request": request, "user": user, "ficha": ficha, "template_schema": template_schema, "extras_map": extras_map},
    )


@router.get("/fichas/{ficha_id}/editar")
def ficha_editar(ficha_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    ficha = get_ficha(db, ficha_id)
    if not ficha:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)
    templates_list = list_templates(db, active_only=True)
    template_schema = normalize_template_schema(ficha.template.schema_json)
    return templates.TemplateResponse(
        "ficha_form.html",
        {
            "request": request,
            "user": user,
            "manual": False,
            "processo": ficha.process,
            "template": ficha.template,
            "template_schema": template_schema,
            "templates_list": templates_list,
            "processos": [],
            "process_filters": {},
            "ficha": ficha,
            "form": ficha.campos_base_json,
            "extras": ficha.extras_json or {},
            "errors": {},
        },
    )


@router.post("/fichas/{ficha_id}/editar")
async def ficha_atualizar(ficha_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    ficha = get_ficha(db, ficha_id)
    if not ficha:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)

    form = await request.form()
    form_data = dict(form)
    errors: dict[str, str] = {}
    status_value = str(form_data.get("status") or ficha.status or "ativo").strip().lower()
    if status_value not in {"ativo", "rascunho", "arquivado"}:
        errors["status"] = "Status invalido"

    base_fields = None
    try:
        base_fields = FichaBaseForm.model_validate(form_data)
    except ValidationError as exc:
        errors.update(validation_errors_to_dict(exc))

    template_schema = normalize_template_schema(ficha.template.schema_json)
    extras_json, extra_errors = parse_extras(form_data, template_schema)
    for key, value in extra_errors.items():
        errors[f"extra__{key}"] = value

    if errors:
        templates_list = list_templates(db, active_only=True)
        return templates.TemplateResponse(
            "ficha_form.html",
            {
                "request": request,
                "user": user,
                "manual": False,
                "processo": ficha.process,
                "template": ficha.template,
                "template_schema": template_schema,
                "templates_list": templates_list,
                "processos": [],
                "process_filters": {},
                "ficha": ficha,
                "form": form_data,
                "extras": extras_json,
                "errors": errors,
            },
            status_code=400,
        )

    ficha = update_ficha(
        db,
        ficha,
        base_fields.model_dump(),
        extras_json,
        form_data.get("indexador"),
        form_data.get("observacoes"),
        status_value,
        user,
    )
    return RedirectResponse(with_prefix(f"/fichas/{ficha.id}"), status_code=303)


@router.post("/fichas/{ficha_id}/excluir")
def ficha_excluir(ficha_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    ficha = get_ficha(db, ficha_id)
    if not ficha:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)
    delete_ficha(db, ficha, user)
    return RedirectResponse(with_prefix("/fichas"), status_code=303)


@router.post("/fichas/{ficha_id}/anexos")
async def ficha_anexar(
    ficha_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    ficha = get_ficha(db, ficha_id)
    if not ficha:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)

    if not file.filename:
        return RedirectResponse(with_prefix(f"/fichas/{ficha.id}"), status_code=303)

    storage = get_storage_backend()
    result = storage.save(file)
    attachment = Attachment(
        ficha_id=ficha.id,
        filename=result.filename,
        content_type=result.content_type,
        size=result.size,
        storage_key=result.storage_key,
    )
    db.add(attachment)
    db.commit()
    return RedirectResponse(with_prefix(f"/fichas/{ficha.id}"), status_code=303)


@router.get("/anexos/{attachment_id}")
def anexo_download(attachment_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    attachment = db.execute(select(Attachment).where(Attachment.id == attachment_id)).scalar_one_or_none()
    if not attachment:
        return RedirectResponse(with_prefix("/fichas"), status_code=303)

    storage = get_storage_backend()
    download_url = storage.get_download_url(attachment.storage_key, attachment.filename)
    if download_url:
        return RedirectResponse(download_url, status_code=302)

    if hasattr(storage, "get_path"):
        return FileResponse(
            storage.get_path(attachment.storage_key),
            media_type=attachment.content_type,
            filename=attachment.filename,
        )

    stream = storage.open(attachment.storage_key)
    headers = {"Content-Disposition": f'attachment; filename="{attachment.filename}"'}
    return StreamingResponse(stream, media_type=attachment.content_type, headers=headers)


@router.get("/admin/templates")
def admin_templates_list(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    templates_list = list_templates(db)
    return templates.TemplateResponse(
        "admin_templates_list.html",
        {"request": request, "user": user, "templates_list": templates_list},
    )


@router.get("/admin/templates/importar")
def admin_template_import_page(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "admin_template_import.html",
        {"request": request, "user": user, "errors": {}, "message": None},
    )


@router.post("/admin/templates/importar")
async def admin_template_import(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    if not file.filename:
        return templates.TemplateResponse(
            "admin_template_import.html",
            {"request": request, "user": user, "errors": {"file": "Arquivo invalido"}, "message": None},
            status_code=400,
        )

    try:
        payload = json.loads((await file.read()).decode("utf-8"))
    except Exception:
        return templates.TemplateResponse(
            "admin_template_import.html",
            {"request": request, "user": user, "errors": {"file": "JSON invalido"}, "message": None},
            status_code=400,
        )

    try:
        template, created = import_template_payload(db, payload, user)
    except Exception as exc:
        return templates.TemplateResponse(
            "admin_template_import.html",
            {"request": request, "user": user, "errors": {"file": str(exc)}, "message": None},
            status_code=400,
        )

    if not created:
        return templates.TemplateResponse(
            "admin_template_import.html",
            {
                "request": request,
                "user": user,
                "errors": {},
                "message": "Template ja existe para essa versao.",
            },
            status_code=200,
        )

    return RedirectResponse(with_prefix(f"/admin/templates/{template.id}/editar"), status_code=303)


@router.post("/admin/templates/{template_id}/status")
async def admin_template_status(template_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    template = get_template(db, template_id)
    if not template:
        return RedirectResponse(with_prefix("/admin/templates"), status_code=303)

    form = await request.form()
    form_data = dict(form)
    active_raw = str(form_data.get("active", "")).strip().lower()
    active = active_raw in {"1", "true", "on", "yes"}
    set_template_active(db, template, active, user)
    return RedirectResponse(with_prefix("/admin/templates"), status_code=303)


@router.get("/admin/templates/novo")
def admin_template_novo(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "admin_template_form.html",
        {"request": request, "user": user, "template": None, "form": {}, "errors": {}},
    )


@router.post("/admin/templates/novo")
async def admin_template_criar(request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    form_data = dict(form)
    try:
        data = TemplateForm.model_validate(form_data)
    except ValidationError as exc:
        errors = validation_errors_to_dict(exc)
        return templates.TemplateResponse(
            "admin_template_form.html",
            {"request": request, "user": user, "template": None, "form": form_data, "errors": errors},
            status_code=400,
        )

    try:
        template = create_template(
            db,
            data.nome,
            data.descricao,
            data.schema_text,
            user,
            origem_pdf=data.origem_pdf,
            versao=data.versao,
            is_active=data.is_active,
        )
    except ValueError as exc:
        errors = {"schema_text": "Schema JSON invalido"}
        if "versao" in str(exc).lower():
            errors = {"versao": str(exc)}
        return templates.TemplateResponse(
            "admin_template_form.html",
            {"request": request, "user": user, "template": None, "form": form_data, "errors": errors},
            status_code=400,
        )

    return RedirectResponse(with_prefix(f"/admin/templates/{template.id}/editar"), status_code=303)


@router.get("/admin/templates/{template_id}/editar")
def admin_template_editar(template_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    template = get_template(db, template_id)
    if not template:
        return RedirectResponse(with_prefix("/admin/templates"), status_code=303)
    return templates.TemplateResponse(
        "admin_template_form.html",
        {
            "request": request,
            "user": user,
            "template": template,
            "form": {
                "nome": template.nome,
                "descricao": template.descricao,
                "origem_pdf": template.origem_pdf,
                "is_active": template.is_active,
                "schema_text": json.dumps(template.schema_json, indent=2),
            },
            "errors": {},
        },
    )


@router.post("/admin/templates/{template_id}/editar")
async def admin_template_atualizar(template_id: str, request: Request, db: Session = Depends(get_db)):
    user = ensure_user(request, db, admin=True)
    if isinstance(user, RedirectResponse):
        return user
    template = get_template(db, template_id)
    if not template:
        return RedirectResponse(with_prefix("/admin/templates"), status_code=303)

    form = await request.form()
    form_data = dict(form)
    try:
        data = TemplateForm.model_validate(form_data)
    except ValidationError as exc:
        errors = validation_errors_to_dict(exc)
        return templates.TemplateResponse(
            "admin_template_form.html",
            {"request": request, "user": user, "template": template, "form": form_data, "errors": errors},
            status_code=400,
        )

    try:
        if data.versao and data.versao <= template.versao:
            raise ValueError("Versao deve ser maior que a atual")
        template = create_template_version(
            db,
            template,
            data.nome,
            data.descricao,
            data.schema_text,
            user,
            origem_pdf=data.origem_pdf,
            is_active=data.is_active,
            versao=data.versao,
        )
    except ValueError as exc:
        errors = {"schema_text": "Schema JSON invalido"}
        if "versao" in str(exc).lower():
            errors = {"versao": str(exc)}
        return templates.TemplateResponse(
            "admin_template_form.html",
            {"request": request, "user": user, "template": template, "form": form_data, "errors": errors},
            status_code=400,
        )

    return RedirectResponse(with_prefix(f"/admin/templates/{template.id}/editar"), status_code=303)
