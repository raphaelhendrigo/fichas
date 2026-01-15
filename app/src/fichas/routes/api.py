from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from fichas.audit import model_to_dict
from fichas.auth import get_current_user
from fichas.db import get_db
from fichas.schemas import FichaOut, ProcessForm, ProcessOut
from fichas.services.fichas_service import list_fichas
from fichas.services.processos_service import create_process, get_process, list_processes, update_process
from fichas.services.templates_service import list_templates

router = APIRouter()


@router.get("/processos", response_model=dict[str, Any])
def api_list_processes(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    page = int(request.query_params.get("page", "1"))
    page_size = int(request.query_params.get("page_size", "20"))
    filters = {
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
    }
    items, total = list_processes(db, filters, page, page_size)
    return {
        "items": [ProcessOut.model_validate(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/processos", response_model=ProcessOut)
def api_create_process(
    payload: ProcessForm,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    process = create_process(db, payload.model_dump(), user)
    return ProcessOut.model_validate(process)


@router.get("/processos/{process_id}", response_model=ProcessOut)
def api_get_process(
    process_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    process = get_process(db, process_id)
    if not process:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processo nao encontrado")
    return ProcessOut.model_validate(process)


@router.patch("/processos/{process_id}", response_model=ProcessOut)
def api_update_process(
    process_id: str,
    payload: ProcessForm,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    process = get_process(db, process_id)
    if not process:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processo nao encontrado")
    process = update_process(db, process, payload.model_dump(), user)
    return ProcessOut.model_validate(process)


@router.get("/fichas", response_model=dict[str, Any])
def api_list_fichas(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    page = int(request.query_params.get("page", "1"))
    page_size = int(request.query_params.get("page_size", "20"))
    filters = {
        "numero": request.query_params.get("numero"),
        "ano": request.query_params.get("ano"),
        "interessado": request.query_params.get("interessado"),
        "assunto": request.query_params.get("assunto"),
        "template_id": request.query_params.get("template_id"),
    }
    items, total = list_fichas(db, filters, page, page_size)
    return {
        "items": [FichaOut.model_validate(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/templates", response_model=list[dict[str, Any]])
def api_list_templates(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(get_current_user)],
):
    templates = list_templates(db)
    return [model_to_dict(template) for template in templates]
