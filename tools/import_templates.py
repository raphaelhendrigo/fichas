from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "app" / "src"))

from sqlalchemy import select

from fichas.db import SessionLocal
from fichas.models import User
from fichas.services.templates_service import import_template_payload


def resolve_user(db, email: str | None):
    if not email:
        return None
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa templates JSON para o banco.")
    parser.add_argument(
        "--path",
        default=str(ROOT / "templates_draft"),
        help="Arquivo JSON ou diretorio com drafts.",
    )
    parser.add_argument("--replace", action="store_true", help="Atualiza se versao ja existir.")
    parser.add_argument("--user-email", default=None, help="Email do usuario para auditoria.")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Caminho nao encontrado: {target}")
        return 1

    files = [target] if target.is_file() else sorted(target.glob("*.json"))
    if not files:
        print("Nenhum JSON encontrado para importar.")
        return 1

    db = SessionLocal()
    try:
        user = resolve_user(db, args.user_email)
        for file_path in files:
            try:
                payload = load_json(file_path)
            except Exception as exc:
                print(f"Erro lendo {file_path}: {exc}")
                continue
            try:
                template, created = import_template_payload(db, payload, user, replace_existing=args.replace)
            except Exception as exc:
                print(f"Erro importando {file_path}: {exc}")
                continue
            status = "criado" if created else "ja existe"
            print(f"{file_path.name}: {template.nome} v{template.versao} ({status})")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
