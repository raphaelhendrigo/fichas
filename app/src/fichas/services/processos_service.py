from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fichas.audit import log_action, model_to_dict
from fichas.models import Process


def list_processes(
    db: Session,
    filters: dict[str, Any],
    page: int,
    page_size: int,
) -> tuple[list[Process], int]:
    query = select(Process)

    numero = filters.get("numero")
    if numero:
        like = f"%{numero}%"
        query = query.where(or_(Process.process_key.ilike(like), Process.tc_numero.ilike(like)))

    ano = filters.get("ano")
    if ano:
        query = query.where(Process.ano == int(ano))

    interessado = filters.get("interessado")
    if interessado:
        query = query.where(Process.interessado.ilike(f"%{interessado}%"))

    assunto = filters.get("assunto")
    if assunto:
        query = query.where(Process.assunto.ilike(f"%{assunto}%"))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = (
        db.execute(
            query.order_by(Process.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return items, total


def get_process(db: Session, process_id):
    return db.execute(select(Process).where(Process.id == process_id)).scalar_one_or_none()


def create_process(db: Session, data: dict[str, Any], user):
    process = Process(**data)
    db.add(process)
    db.flush()
    log_action(db, user, "create", "process", str(process.id), None, model_to_dict(process))
    db.commit()
    db.refresh(process)
    return process


def update_process(db: Session, process: Process, data: dict[str, Any], user):
    before = model_to_dict(process)
    for key, value in data.items():
        setattr(process, key, value)
    db.add(process)
    db.flush()
    after = model_to_dict(process)
    log_action(db, user, "update", "process", str(process.id), before, after)
    db.commit()
    db.refresh(process)
    return process
