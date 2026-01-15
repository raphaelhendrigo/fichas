from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from fichas.audit import log_action, model_to_dict
from fichas.models import FichaTemplate
from fichas.schemas import parse_template_schema


def list_templates(db: Session) -> list[FichaTemplate]:
    return db.execute(select(FichaTemplate).order_by(FichaTemplate.nome.asc())).scalars().all()


def get_template(db: Session, template_id):
    return db.execute(select(FichaTemplate).where(FichaTemplate.id == template_id)).scalar_one_or_none()


def create_template(db: Session, nome: str, descricao: str | None, schema_text: str, user):
    fields = parse_template_schema(schema_text)
    template = FichaTemplate(
        nome=nome,
        descricao=descricao,
        schema_json=[field.model_dump() for field in fields],
    )
    db.add(template)
    db.flush()
    log_action(db, user, "create", "template", str(template.id), None, model_to_dict(template))
    db.commit()
    db.refresh(template)
    return template


def update_template(db: Session, template: FichaTemplate, nome: str, descricao: str | None, schema_text: str, user):
    fields = parse_template_schema(schema_text)
    before = model_to_dict(template)
    template.nome = nome
    template.descricao = descricao
    template.schema_json = [field.model_dump() for field in fields]
    db.add(template)
    db.flush()
    after = model_to_dict(template)
    log_action(db, user, "update", "template", str(template.id), before, after)
    db.commit()
    db.refresh(template)
    return template
