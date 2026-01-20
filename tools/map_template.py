from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if ord(ch) < 128)
    ascii_text = ascii_text.strip().lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return ascii_text or "campo"


def prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{text}{suffix}: ").strip()
    return value if value else (default or "")


def prompt_bool(text: str, default: bool) -> bool:
    suffix = "s" if default else "n"
    value = input(f"{text} (s/n) [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"s", "sim", "y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ajusta drafts de template via prompts.")
    parser.add_argument("input", help="Arquivo JSON draft.")
    parser.add_argument("--output", default=None, help="Arquivo de saida (opcional).")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Arquivo nao encontrado: {input_path}")
        return 1

    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    sections = payload.get("sections") or []
    if not sections:
        print("JSON sem sections. Nada para ajustar.")
        return 1

    seen_ids = {field.get("id") for section in sections for field in section.get("fields", [])}
    for section in sections:
        print(f"\nSecao: {section.get('label')}")
        for field in section.get("fields", []):
            print(f"- Campo atual: {field.get('label')} (id={field.get('id')}, type={field.get('type')})")
            new_label = prompt("  Novo rotulo", field.get("label", ""))
            if new_label and new_label != field.get("label"):
                field["label"] = new_label
                if prompt_bool("  Atualizar id baseado no rotulo?", False):
                    new_id = slugify(new_label)
                    if new_id in seen_ids:
                        suffix = 2
                        while f"{new_id}_{suffix}" in seen_ids:
                            suffix += 1
                        new_id = f"{new_id}_{suffix}"
                    seen_ids.add(new_id)
                    field["id"] = new_id

            new_type = prompt("  Novo tipo", field.get("type", "text"))
            if new_type:
                field["type"] = new_type

            field["required"] = prompt_bool("  Obrigatorio?", bool(field.get("required", False)))

            if field.get("type") == "enum":
                options_raw = prompt("  Opcoes (separadas por virgula)", "")
                if options_raw:
                    field["options"] = [opt.strip() for opt in options_raw.split(",") if opt.strip()]

    output_path = Path(args.output) if args.output else input_path
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)

    print(f"Arquivo salvo em: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
