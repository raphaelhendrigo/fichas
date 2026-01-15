from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.append(str(root / "src"))

from sqlalchemy import select

from fichas.auth import get_password_hash
from fichas.db import SessionLocal
from fichas.models import FichaTemplate, User
from fichas.settings import settings


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
            "schema_json": [
                {"name": "numero_convite", "label": "Numero do convite", "type": "text", "required": True},
                {"name": "tipo_encadernacao", "label": "Tipo de encadernacao", "type": "text", "required": False},
                {"name": "quantidade", "label": "Quantidade", "type": "number", "required": False},
                {"name": "prazo", "label": "Prazo", "type": "date", "required": False},
                {"name": "responsavel", "label": "Responsavel", "type": "text", "required": False},
            ],
        },
        {
            "nome": "Aposentadoria",
            "descricao": "Campos para ficha de aposentadoria",
            "schema_json": [
                {"name": "servidor", "label": "Servidor", "type": "text", "required": True},
                {"name": "matricula", "label": "Matricula", "type": "text", "required": False},
                {"name": "cargo", "label": "Cargo", "type": "text", "required": False},
                {"name": "data_ingresso", "label": "Data de ingresso", "type": "date", "required": False},
                {"name": "tempo_contribuicao", "label": "Tempo de contribuicao", "type": "number", "required": False},
                {"name": "fundamento_legal", "label": "Fundamento legal", "type": "text", "required": False},
            ],
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
        )
        db.add(template)
        db.commit()
        print(f"Template {item['nome']} criado.")


def main():
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_templates(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
