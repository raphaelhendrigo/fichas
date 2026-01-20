from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Mapping

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fichas.audit import log_action, model_to_dict
from fichas.models import Ficha, FichaTemplate, Process
from fichas.schemas import TemplateField, TemplateSchema, flatten_template_fields


def _normalize_json(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_json_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_json(value) for key, value in data.items()}


def _parse_decimal(raw: str) -> Decimal:
    cleaned = raw.strip().replace("R$", "").replace(" ", "")
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "sim", "yes", "on"}:
        return True
    if value in {"0", "false", "nao", "no", "off"}:
        return False
    return bool(value)


def _validate_field_value(field: TemplateField, value: Any) -> str | None:
    validations = field.validations
    if not validations or value is None:
        return None
    if isinstance(value, str):
        if validations.min_length is not None and len(value) < validations.min_length:
            return f"Minimo de {validations.min_length} caracteres"
        if validations.max_length is not None and len(value) > validations.max_length:
            return f"Maximo de {validations.max_length} caracteres"
        if validations.regex and not re.fullmatch(validations.regex, value):
            return "Formato invalido"
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        if validations.min_value is not None and number < validations.min_value:
            return f"Minimo {validations.min_value}"
        if validations.max_value is not None and number > validations.max_value:
            return f"Maximo {validations.max_value}"
    return None


def parse_extras(form: Mapping[str, Any], schema: TemplateSchema) -> tuple[dict[str, Any], dict[str, str]]:
    extras: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for field in flatten_template_fields(schema):
        key = f"extra__{field.field_id}"
        raw = form.get(key)
        if isinstance(raw, list):
            raw = raw[0]

        if raw is None or str(raw).strip() == "":
            if field.required:
                errors[field.field_id] = "Obrigatorio"
            else:
                extras[field.field_id] = None
            continue

        try:
            if field.type in {"number", "currency"}:
                extras[field.field_id] = float(_parse_decimal(str(raw)))
            elif field.type == "date":
                extras[field.field_id] = date.fromisoformat(str(raw)).isoformat()
            elif field.type == "boolean":
                extras[field.field_id] = _parse_bool(str(raw))
            elif field.type == "enum":
                value = str(raw).strip()
                if field.options and value not in field.options:
                    raise ValueError("Opcao invalida")
                extras[field.field_id] = value
            else:
                extras[field.field_id] = str(raw).strip()
        except ValueError:
            errors[field.field_id] = "Valor invalido"
            continue

        error = _validate_field_value(field, extras[field.field_id])
        if error:
            errors[field.field_id] = error

    return extras, errors


def list_fichas(db: Session, filters: dict[str, Any], page: int, page_size: int) -> tuple[list[Ficha], int]:
    query = select(Ficha).join(Process).join(FichaTemplate)

    query_text = filters.get("q")
    if query_text:
        like = f"%{query_text}%"
        query = query.where(
            or_(
                Process.process_key.ilike(like),
                Process.tc_numero.ilike(like),
                Process.interessado.ilike(like),
                Process.assunto.ilike(like),
                Process.procedencia.ilike(like),
                Process.reparticao.ilike(like),
                Ficha.indexador.ilike(like),
            )
        )

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

    status = filters.get("status")
    if status:
        query = query.where(Ficha.status == status)

    data_inicio = filters.get("data_inicio")
    if data_inicio:
        query = query.where(Process.data >= data_inicio)

    data_fim = filters.get("data_fim")
    if data_fim:
        query = query.where(Process.data <= data_fim)

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
    status: str | None,
    user,
) -> Ficha:
    ficha = Ficha(
        process_id=process.id,
        template_id=template.id,
        template_version=template.versao,
        indexador=indexador,
        campos_base_json=normalize_json_dict(base_fields),
        extras_json=extras_json,
        observacoes=observacoes,
        status=status or "ativo",
        created_by_id=user.id if user else None,
        updated_by_id=user.id if user else None,
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
    status: str | None,
    user,
) -> Ficha:
    before = model_to_dict(ficha)
    ficha.indexador = indexador
    ficha.campos_base_json = normalize_json_dict(base_fields)
    ficha.extras_json = extras_json
    ficha.observacoes = observacoes
    if status:
        ficha.status = status
    ficha.updated_by_id = user.id if user else ficha.updated_by_id
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
