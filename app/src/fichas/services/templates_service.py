from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from fichas.audit import log_action, model_to_dict
from fichas.models import FichaTemplate
from fichas.schemas import TemplateDraft, TemplateSchema, normalize_template_schema, parse_template_schema


def list_templates(db: Session, active_only: bool | None = None) -> list[FichaTemplate]:
    query = select(FichaTemplate)
    if active_only is True:
        query = query.where(FichaTemplate.is_active.is_(True))
    query = query.order_by(FichaTemplate.nome.asc(), FichaTemplate.versao.desc())
    return db.execute(query).scalars().all()


def get_template(db: Session, template_id):
    return db.execute(select(FichaTemplate).where(FichaTemplate.id == template_id)).scalar_one_or_none()


def get_latest_version(db: Session, nome: str) -> int:
    return db.execute(select(func.max(FichaTemplate.versao)).where(FichaTemplate.nome == nome)).scalar() or 0


def _load_schema(schema_input: str | dict[str, Any] | TemplateSchema) -> TemplateSchema:
    if isinstance(schema_input, TemplateSchema):
        return schema_input
    if isinstance(schema_input, str):
        return parse_template_schema(schema_input)
    return normalize_template_schema(schema_input)


def _deactivate_other_versions(db: Session, nome: str, keep_id) -> None:
    db.execute(
        update(FichaTemplate)
        .where(FichaTemplate.nome == nome, FichaTemplate.id != keep_id)
        .values(is_active=False)
    )


def create_template(
    db: Session,
    nome: str,
    descricao: str | None,
    schema_input: str | dict[str, Any] | TemplateSchema,
    user,
    origem_pdf: str | None = None,
    versao: int | None = None,
    is_active: bool = True,
):
    schema = _load_schema(schema_input)
    versao = versao or (get_latest_version(db, nome) + 1)
    exists = (
        db.execute(select(FichaTemplate).where(FichaTemplate.nome == nome, FichaTemplate.versao == versao))
        .scalar_one_or_none()
    )
    if exists:
        raise ValueError("Template com essa versao ja existe")
    template = FichaTemplate(
        nome=nome,
        descricao=descricao,
        versao=versao,
        origem_pdf=origem_pdf,
        is_active=is_active,
        schema_json=schema.model_dump(by_alias=True),
    )
    db.add(template)
    db.flush()
    log_action(db, user, "create", "template", str(template.id), None, model_to_dict(template))
    if is_active:
        _deactivate_other_versions(db, nome, template.id)
    db.commit()
    db.refresh(template)
    return template


def create_template_version(
    db: Session,
    template: FichaTemplate,
    nome: str,
    descricao: str | None,
    schema_input: str | dict[str, Any] | TemplateSchema,
    user,
    origem_pdf: str | None = None,
    is_active: bool = True,
    versao: int | None = None,
):
    return create_template(
        db,
        nome=nome,
        descricao=descricao,
        schema_input=schema_input,
        user=user,
        origem_pdf=origem_pdf or template.origem_pdf,
        versao=versao or (template.versao + 1),
        is_active=is_active,
    )


def set_template_active(db: Session, template: FichaTemplate, active: bool, user):
    before = model_to_dict(template)
    template.is_active = active
    db.add(template)
    db.flush()
    if active:
        _deactivate_other_versions(db, template.nome, template.id)
    after = model_to_dict(template)
    log_action(db, user, "update", "template", str(template.id), before, after)
    db.commit()
    db.refresh(template)
    return template


def import_template_payload(db: Session, payload: dict[str, Any], user, replace_existing: bool = False):
    draft = TemplateDraft.model_validate(payload)
    schema = TemplateSchema(sections=draft.sections)
    versao = draft.versao or (get_latest_version(db, draft.nome) + 1)
    existing = (
        db.execute(select(FichaTemplate).where(FichaTemplate.nome == draft.nome, FichaTemplate.versao == versao))
        .scalar_one_or_none()
    )
    if existing and not replace_existing:
        return existing, False
    if existing and replace_existing:
        before = model_to_dict(existing)
        existing.descricao = draft.descricao
        existing.origem_pdf = draft.origem_pdf
        existing.is_active = draft.is_active
        existing.schema_json = schema.model_dump(by_alias=True)
        db.add(existing)
        db.flush()
        after = model_to_dict(existing)
        log_action(db, user, "update", "template", str(existing.id), before, after)
        if existing.is_active:
            _deactivate_other_versions(db, existing.nome, existing.id)
        db.commit()
        db.refresh(existing)
        return existing, True
    template = create_template(
        db,
        nome=draft.nome,
        descricao=draft.descricao,
        schema_input=schema,
        user=user,
        origem_pdf=draft.origem_pdf,
        versao=versao,
        is_active=draft.is_active,
    )
    return template, True
