from __future__ import annotations

import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.append(str(root / "src"))

from sqlalchemy import select

from fichas.auth import get_password_hash
from fichas.db import SessionLocal
from fichas.models import FichaTemplate, User
from fichas.settings import settings
from fichas.services.templates_service import import_template_payload


def seed_admin(db):
    user = db.execute(select(User).where(User.email == settings.ADMIN_SEED_EMAIL)).scalar_one_or_none()
    if not user:
        user = User(
            email=settings.ADMIN_SEED_EMAIL,
            hashed_password=get_password_hash(settings.ADMIN_SEED_PASSWORD),
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print("Admin criado.")
    else:
        print("Admin ja existe.")


def seed_templates(db):
    templates = [
        {
            "nome": "Carta Convite/Encadernacao",
            "descricao": "Campos para carta convite e encadernacao",
            "versao": 1,
            "origem_pdf": None,
            "schema_json": {
                "sections": [
                    {
                        "id": "geral",
                        "label": "Geral",
                        "order": 1,
                        "fields": [
                            {"id": "numero_convite", "label": "Numero do convite", "type": "text", "required": True},
                            {"id": "tipo_encadernacao", "label": "Tipo de encadernacao", "type": "text"},
                            {"id": "quantidade", "label": "Quantidade", "type": "number"},
                            {"id": "prazo", "label": "Prazo", "type": "date"},
                            {"id": "responsavel", "label": "Responsavel", "type": "text"},
                        ],
                    }
                ]
            },
        },
        {
            "nome": "Aposentadoria",
            "descricao": "Campos para ficha de aposentadoria",
            "versao": 1,
            "origem_pdf": None,
            "schema_json": {
                "sections": [
                    {
                        "id": "servidor",
                        "label": "Servidor",
                        "order": 1,
                        "fields": [
                            {"id": "servidor", "label": "Servidor", "type": "text", "required": True},
                            {"id": "matricula", "label": "Matricula", "type": "text"},
                            {"id": "cargo", "label": "Cargo", "type": "text"},
                            {"id": "data_ingresso", "label": "Data de ingresso", "type": "date"},
                            {"id": "tempo_contribuicao", "label": "Tempo de contribuicao", "type": "number"},
                            {"id": "fundamento_legal", "label": "Fundamento legal", "type": "text"},
                        ],
                    }
                ]
            },
        },
    ]

    for item in templates:
        exists = db.execute(select(FichaTemplate).where(FichaTemplate.nome == item["nome"])).scalar_one_or_none()
        if exists:
            print(f"Template {item['nome']} ja existe.")
            continue
        template = FichaTemplate(
            nome=item["nome"],
            descricao=item["descricao"],
            schema_json=item["schema_json"],
            versao=item["versao"],
            origem_pdf=item["origem_pdf"],
            is_active=True,
        )
        db.add(template)
        db.commit()
        print(f"Template {item['nome']} criado.")


def seed_draft_templates(db):
    if os.getenv("IMPORT_DRAFT_TEMPLATES", "").lower() not in {"1", "true", "yes"}:
        return
    project_root = Path(__file__).resolve().parents[2]
    drafts_dir = project_root / "templates_draft"
    if not drafts_dir.exists():
        print("templates_draft nao encontrado.")
        return

    for draft_path in sorted(drafts_dir.glob("*.json")):
        try:
            payload = json.loads(draft_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Draft invalido: {draft_path.name}")
            continue
        template, created = import_template_payload(db, payload, user=None)
        status = "importado" if created else "ja existe"
        print(f"Draft {draft_path.name}: {template.nome} v{template.versao} ({status})")


def main():
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_templates(db)
        seed_draft_templates(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
