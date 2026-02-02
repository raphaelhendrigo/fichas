from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz, process

from fichas.schemas import TemplateSchema


def build_ocr_result(ocr_items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    extracted_text = "\n".join(item["text"] for item in ocr_items if item.get("text"))
    return extracted_text, ocr_items


def _normalize_label(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_date(value: str) -> str | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> str | None:
    cleaned = value.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    cleaned = re.sub(r"[^0-9\.-]", "", cleaned)
    if not cleaned:
        return None
    return cleaned


def _parse_year(value: str) -> str | None:
    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return None
    return match.group(0)


def _extract_key_values(lines: list[str]) -> list[tuple[str, str, str]]:
    pairs = []
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        match = re.match(r"^\s*([^:]{2,60})\s*:\s*(.+)$", raw)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            pairs.append((key, value, raw))
    return pairs


def _line_confidence(line: str, ocr_items: list[dict[str, Any]]) -> float:
    if not ocr_items:
        return 0.4
    candidates = [item["text"] for item in ocr_items if item.get("text")]
    best = process.extractOne(line, candidates, scorer=fuzz.token_set_ratio)
    if not best:
        return 0.4
    _best_text, score, index = best
    conf = float(ocr_items[index].get("confidence") or 0.4)
    if score < 70:
        conf *= 0.7
    return conf


def _confidence_badge(conf: float, matched_score: float) -> float:
    boost = 0.1 if matched_score >= 85 else 0.0
    penalty = 0.1 if matched_score < 75 else 0.0
    return max(0.05, min(1.0, conf + boost - penalty))


def map_fields_to_ficha(
    text: str,
    ocr_items: list[dict[str, Any]],
    template: TemplateSchema | None,
) -> dict[str, dict[str, dict[str, Any]]]:
    lines = [line for line in text.splitlines() if line.strip()]
    pairs = _extract_key_values(lines)

    base_labels = {
        "process_key": [
            "processo",
            "processo chave",
            "chave do processo",
            "numero do processo",
            "numero processo",
            "proc",
        ],
        "tc_numero": ["tc numero", "tc", "tcm", "numero tc"],
        "ano": ["ano", "exercicio"],
        "data": ["data", "data do processo", "data de abertura"],
        "interessado": ["interessado", "requerente", "interessados"],
        "assunto": ["assunto", "objeto"],
        "procedencia": ["procedencia", "procedencia", "origem"],
        "reparticao": ["reparticao", "reparticao", "setor", "unidade"],
        "valor": ["valor", "valor total", "montante", "quantia"],
        "observacoes": ["observacoes", "observacao", "anotacoes"],
        "indexador": ["indexador"],
    }

    label_map: dict[str, tuple[str, str]] = {}
    for field, labels in base_labels.items():
        for label in labels:
            label_map[_normalize_label(label)] = ("base", field)

    template_fields: dict[str, str] = {}
    if template:
        for section in template.sections:
            for field in section.fields:
                template_fields[field.field_id] = field.type
                for label in (field.label, field.field_id):
                    label_map[_normalize_label(label)] = ("extras", field.field_id)

    suggestions = {"base": {}, "extras": {}}

    for key, value, raw in pairs:
        key_norm = _normalize_label(key)
        choices = list(label_map.keys())
        best = process.extractOne(key_norm, choices, scorer=fuzz.token_set_ratio)
        if not best:
            continue
        label, score, _ = best
        if score < 70:
            continue
        group, field = label_map[label]
        conf = _line_confidence(raw, ocr_items)
        conf = _confidence_badge(conf, score)
        parsed_value = _parse_value(field, value, template_fields)
        if parsed_value is None:
            continue
        existing = suggestions[group].get(field)
        if not existing or conf > existing.get("confidence", 0):
            suggestions[group][field] = {
                "value": parsed_value,
                "confidence": conf,
                "source": "key_value",
            }

    _apply_regex_fallbacks(text, suggestions)
    return suggestions


def _parse_value(field: str, value: str, template_fields: dict[str, str]) -> str | None:
    if field == "ano":
        return _parse_year(value)
    if field == "data":
        return _parse_date(value)
    if field == "valor":
        return _parse_decimal(value)
    if field in template_fields:
        field_type = template_fields[field]
        if field_type in {"date"}:
            return _parse_date(value)
        if field_type in {"number", "currency"}:
            return _parse_decimal(value)
        if field_type == "boolean":
            lowered = value.strip().lower()
            if lowered in {"sim", "true", "1", "yes"}:
                return "true"
            if lowered in {"nao", "false", "0", "no"}:
                return "false"
            return None
    return value.strip() or None


def _apply_regex_fallbacks(text: str, suggestions: dict[str, dict[str, dict[str, Any]]]) -> None:
    base = suggestions["base"]
    if "tc_numero" not in base:
        match = re.search(r"\bTC\s*\d{2,}\b", text, flags=re.IGNORECASE)
        if match:
            base["tc_numero"] = {
                "value": match.group(0).replace(" ", ""),
                "confidence": 0.35,
                "source": "heuristic",
            }
    if "ano" not in base:
        match = re.search(r"(19|20)\d{2}", text)
        if match:
            base["ano"] = {"value": match.group(0), "confidence": 0.3, "source": "heuristic"}
