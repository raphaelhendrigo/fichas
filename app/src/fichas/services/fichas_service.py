from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fichas.audit import log_action, model_to_dict
from fichas.models import Ficha, FichaTemplate, Process
from fichas.schemas import TemplateField


def _normalize_json(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_json_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_json(value) for key, value in data.items()}


def parse_extras(form: Mapping[str, Any], fields: list[TemplateField]) -> tuple[dict[str, Any], dict[str, str]]:
    extras: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for field in fields:
        key = f"extra__{field.name}"
        raw = form.get(key)
        if isinstance(raw, list):
            raw = raw[0]

        if raw is None or str(raw).strip() == "":
            if field.required:
                errors[field.name] = "Obrigatorio"
            else:
                extras[field.name] = None
            continue

        try:
            if field.type == "number":
                extras[field.name] = float(str(raw).replace(",", "."))
            elif field.type == "date":
                extras[field.name] = date.fromisoformat(str(raw)).isoformat()
            else:
                extras[field.name] = str(raw).strip()
        except ValueError:
            errors[field.name] = "Valor invalido"

    return extras, errors


def list_fichas(db: Session, filters: dict[str, Any], page: int, page_size: int) -> tuple[list[Ficha], int]:
    query = select(Ficha).join(Process).join(FichaTemplate)

    numero = filters.get("numero")
    if numero:
        like = f"%{numero}%"
        query = query.where((Process.process_key.ilike(like)) | (Process.tc_numero.ilike(like)))

    ano = filters.get("ano")
    if ano:
        query = query.where(Process.ano == int(ano))

    interessado = filters.get("interessado")
    if interessado:
        query = query.where(Process.interessado.ilike(f"%{interessado}%"))

    assunto = filters.get("assunto")
    if assunto:
        query = query.where(Process.assunto.ilike(f"%{assunto}%"))

    indexador = filters.get("indexador")
    if indexador:
        query = query.where(Ficha.indexador.ilike(f"%{indexador}%"))

    template_id = filters.get("template_id")
    if template_id:
        query = query.where(Ficha.template_id == template_id)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = (
        db.execute(query.order_by(Ficha.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return items, total


def get_ficha(db: Session, ficha_id):
    return db.execute(select(Ficha).where(Ficha.id == ficha_id)).scalar_one_or_none()


def create_ficha(
    db: Session,
    process: Process,
    template: FichaTemplate,
    base_fields: dict[str, Any],
    extras_json: dict[str, Any],
    indexador: str | None,
    observacoes: str | None,
    user,
) -> Ficha:
    ficha = Ficha(
        process_id=process.id,
        template_id=template.id,
        indexador=indexador,
        campos_base_json=normalize_json_dict(base_fields),
        extras_json=extras_json,
        observacoes=observacoes,
    )
    db.add(ficha)
    db.flush()
    log_action(db, user, "create", "ficha", str(ficha.id), None, model_to_dict(ficha))
    db.commit()
    db.refresh(ficha)
    return ficha


def update_ficha(
    db: Session,
    ficha: Ficha,
    base_fields: dict[str, Any],
    extras_json: dict[str, Any],
    indexador: str | None,
    observacoes: str | None,
    user,
) -> Ficha:
    before = model_to_dict(ficha)
    ficha.indexador = indexador
    ficha.campos_base_json = normalize_json_dict(base_fields)
    ficha.extras_json = extras_json
    ficha.observacoes = observacoes
    db.add(ficha)
    db.flush()
    after = model_to_dict(ficha)
    log_action(db, user, "update", "ficha", str(ficha.id), before, after)
    db.commit()
    db.refresh(ficha)
    return ficha


def delete_ficha(db: Session, ficha: Ficha, user) -> None:
    before = model_to_dict(ficha)
    db.delete(ficha)
    log_action(db, user, "delete", "ficha", str(ficha.id), before, None)
    db.commit()
