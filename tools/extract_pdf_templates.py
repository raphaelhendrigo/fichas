from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pdfplumber


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if ord(ch) < 128)
    ascii_text = ascii_text.strip().lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return ascii_text or "campo"


def is_section(line: str) -> bool:
    if len(line) < 3 or len(line) > 80:
        return False
    letters = [ch for ch in line if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(ch.isupper() for ch in letters) / len(letters)
    return upper_ratio >= 0.8 and len(line.split()) <= 10


def infer_type(label: str) -> str:
    lower = label.lower()
    if "data" in lower:
        return "date"
    if any(word in lower for word in ("valor", "preco", "custo")):
        return "currency"
    if any(word in lower for word in ("quantidade", "qtd", "tempo", "idade", "ano")):
        return "number"
    if "sim" in lower and "nao" in lower:
        return "boolean"
    if any(word in lower for word in ("observacao", "descricao", "justificativa")):
        return "textarea"
    return "text"


def extract_fields_from_line(line: str) -> list[str]:
    fields: list[str] = []
    parts = re.split(r"\s{2,}", line)
    for part in parts:
        if ":" in part:
            label = part.split(":", 1)[0].strip()
            if len(label) >= 2:
                fields.append(label)
    if fields:
        return fields
    match = re.match(r"(.+?)_{3,}", line)
    if match:
        label = match.group(1).strip()
        if len(label) >= 2:
            fields.append(label)
    return fields


def extract_template_from_pdf(pdf_path: Path) -> dict:
    sections: list[dict] = []
    current_section = {
        "id": "geral",
        "label": "Geral",
        "order": 1,
        "fields": [],
    }
    sections.append(current_section)
    seen_ids: dict[str, int] = {}
    field_order = 1
    section_order = 1

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if is_section(line):
                    section_order += 1
                    current_section = {
                        "id": slugify(line),
                        "label": line.title(),
                        "order": section_order,
                        "fields": [],
                    }
                    sections.append(current_section)
                    field_order = 1
                    continue

                labels = extract_fields_from_line(line)
                for label in labels:
                    field_id = slugify(label)
                    if field_id in seen_ids:
                        seen_ids[field_id] += 1
                        field_id = f"{field_id}_{seen_ids[field_id]}"
                    else:
                        seen_ids[field_id] = 1
                    current_section["fields"].append(
                        {
                            "id": field_id,
                            "label": label.strip(),
                            "type": infer_type(label),
                            "required": False,
                            "layout": {"order": field_order},
                        }
                    )
                    field_order += 1

    sections_with_fields = [section for section in sections if section.get("fields")]
    if not sections_with_fields:
        sections_with_fields = [
            {
                "id": "geral",
                "label": "Geral",
                "order": 1,
                "fields": [],
            }
        ]

    return {
        "nome": pdf_path.stem,
        "descricao": "Draft extraido automaticamente do PDF.",
        "versao": 1,
        "origem_pdf": pdf_path.name,
        "is_active": False,
        "sections": sections_with_fields,
        "gerado_em": datetime.utcnow().isoformat() + "Z",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai drafts de templates a partir de PDFs.")
    parser.add_argument(
        "--input",
        default=str(Path.cwd() / "exemplos"),
        help="Diretorio com PDFs de exemplo.",
    )
    parser.add_argument(
        "--output",
        default=str(Path.cwd() / "templates_draft"),
        help="Diretorio de saida para JSONs.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"Nenhum PDF encontrado em {input_dir}")
        return 1

    for pdf_path in pdf_files:
        payload = extract_template_from_pdf(pdf_path)
        output_path = output_dir / f"{pdf_path.stem}.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
        print(f"Gerado: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
