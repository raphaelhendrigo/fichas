from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz, process

from fichas.schemas import TemplateSchema


def build_ocr_result(ocr_items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    extracted_text = "\n".join(item["text"] for item in ocr_items if item.get("text"))
    return extracted_text, ocr_items


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_label(value: str) -> str:
    value = _strip_accents(value).lower().strip()
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_date(value: str) -> str | None:
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d.%m.%y",
    ):
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


def _parse_tc_numero(value: str) -> str | None:
    match = re.search(r"\d{1,7}[./-]\d{2,4}", value)
    if match:
        return match.group(0)
    match = re.search(r"\d{3,}", value)
    if match:
        return match.group(0)
    return None


def _parse_process_key(value: str) -> str | None:
    match = re.search(r"\d[\d./*-]+", value)
    if match:
        return match.group(0)
    return None


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


def _tokenize_line(line: str) -> tuple[list[str], list[str]]:
    tokens = [token for token in re.split(r"\s+", line.strip()) if token]
    normalized = [_normalize_label(token) for token in tokens]
    return tokens, normalized


def _match_inline_label(
    line: str,
    alias_tokens: list[tuple[list[str], str, str]],
    label_map: dict[str, tuple[str, str]],
) -> tuple[str, str, str, float] | None:
    tokens, norm_tokens = _tokenize_line(line)
    if not norm_tokens:
        return None
    for alias, group, field in alias_tokens:
        if len(norm_tokens) >= len(alias) and norm_tokens[: len(alias)] == alias:
            value = " ".join(tokens[len(alias) :]).strip()
            return group, field, value, 100.0
    if len(norm_tokens) <= 2:
        norm_line = " ".join(norm_tokens)
        best = process.extractOne(norm_line, list(label_map.keys()), scorer=fuzz.token_set_ratio)
        if best and best[1] >= 85:
            group, field = label_map[best[0]]
            return group, field, "", float(best[1])
    return None


def _block_confidence(lines: list[str], ocr_items: list[dict[str, Any]]) -> float:
    if not lines:
        return 0.4
    scores = [_line_confidence(line, ocr_items) for line in lines if line.strip()]
    if not scores:
        return 0.4
    return sum(scores) / len(scores)


def _collect_label_blocks(
    lines: list[str],
    alias_tokens: list[tuple[list[str], str, str]],
    label_map: dict[str, tuple[str, str]],
    ocr_items: list[dict[str, Any]],
) -> list[tuple[str, str, str, float]]:
    results: list[tuple[str, str, str, float]] = []
    current: tuple[str, str, float] | None = None
    buffer: list[str] = []

    def flush():
        nonlocal current, buffer
        if current and buffer:
            group, field, score = current
            value = " ".join(buffer).strip()
            conf = _block_confidence(buffer, ocr_items)
            conf = _confidence_badge(conf, score)
            results.append((group, field, value, conf))
        current = None
        buffer = []

    for line in lines:
        if not line.strip():
            flush()
            continue
        match = _match_inline_label(line, alias_tokens, label_map)
        if match:
            flush()
            group, field, value, score = match
            if value:
                conf = _line_confidence(line, ocr_items)
                conf = _confidence_badge(conf, score)
                results.append((group, field, value, conf))
            else:
                current = (group, field, score)
            continue
        if current:
            buffer.append(line.strip())
    flush()
    return results


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
        "observacoes": ["observacoes", "observacao", "anotacoes", "obs"],
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

    alias_tokens: list[tuple[list[str], str, str]] = []
    for label, (group, field) in label_map.items():
        alias = label.split()
        if not alias:
            continue
        alias_tokens.append((alias, group, field))
    alias_tokens.sort(key=lambda item: len(item[0]), reverse=True)

    def add_suggestion(group: str, field: str, value: str, confidence: float, source: str) -> None:
        if field == "reparticao" and re.match(r"(?i)^valor\\b", value.strip()):
            return
        parsed_value = _parse_value(field, value, template_fields)
        if parsed_value is None:
            return
        existing = suggestions[group].get(field)
        if not existing or confidence > existing.get("confidence", 0):
            suggestions[group][field] = {
                "value": parsed_value,
                "confidence": confidence,
                "source": source,
            }

    blocks = _collect_label_blocks(lines, alias_tokens, label_map, ocr_items)
    for group, field, value, confidence in blocks:
        add_suggestion(group, field, value, confidence, "label_block")

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
        add_suggestion(group, field, value, conf, "key_value")

    label_positions: dict[str, int] = {}
    label_matches: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        match = _match_inline_label(line, alias_tokens, label_map)
        if match:
            group, field, value, score = match
            label_matches.append(
                {
                    "index": idx,
                    "field": field,
                    "value": value,
                    "score": score,
                }
            )
            if not value and field not in label_positions:
                label_positions[field] = idx

    def is_label_index(index: int) -> bool:
        for item in label_matches:
            if item["index"] == index:
                return True
        return False

    def looks_like_date(value: str) -> bool:
        return bool(re.search(r"\b[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}\b", value))

    def looks_like_year(value: str) -> bool:
        return bool(re.search(r"\b(19|20)\d{2}\b", value))

    def looks_like_value(value: str) -> bool:
        return bool(re.search(r"\b[0-9]{1,3}([.,][0-9]{3})+[,\\.][0-9]{2}\b", value))

    def looks_like_proc(value: str) -> bool:
        return bool(re.search(r"\bPROC\\b", value, flags=re.IGNORECASE))

    def is_short_connector(value: str) -> bool:
        return _normalize_label(value) in {"do", "da", "de", "dos", "das", "no", "na", "nos", "nas", "e"}

    if "interessado" not in suggestions["base"]:
        idx = label_positions.get("interessado")
        if idx is not None:
            for j in range(idx + 1, min(len(lines), idx + 8)):
                line = lines[j].strip()
                if is_label_index(j):
                    continue
                if len(line) < 3:
                    continue
                if not re.search(r"[A-Za-z]", line):
                    continue
                if looks_like_year(line) or looks_like_date(line) or looks_like_value(line) or looks_like_proc(line):
                    continue
                conf = _line_confidence(line, ocr_items)
                add_suggestion("base", "interessado", line, conf, "layout_hint")
                break

    if "assunto" not in suggestions["base"]:
        idx = label_positions.get("assunto")
        if idx is not None:
            collected: list[str] = []
            for j in range(idx + 1, len(lines)):
                line = lines[j].strip()
                if is_label_index(j):
                    field = None
                    for item in label_matches:
                        if item["index"] == j:
                            field = item["field"]
                            break
                    if field in {"observacoes", "process_key"}:
                        break
                    continue
                if len(line) < 3 and not is_short_connector(line):
                    continue
                if not re.search(r"[A-Za-z]", line):
                    continue
                if looks_like_year(line) or looks_like_date(line) or looks_like_value(line) or looks_like_proc(line):
                    continue
                collected.append(line)
            if collected:
                conf = _block_confidence(collected, ocr_items)
                add_suggestion("base", "assunto", " ".join(collected), conf, "layout_hint")

    if "observacoes" not in suggestions["base"]:
        idx = label_positions.get("observacoes")
        if idx is not None:
            for j in range(idx + 1, min(len(lines), idx + 4)):
                line = lines[j].strip()
                if is_label_index(j):
                    continue
                if len(line) < 2:
                    continue
                conf = _line_confidence(line, ocr_items)
                add_suggestion("base", "observacoes", line, conf, "layout_hint")
                break

    _apply_regex_fallbacks(text, suggestions)
    return suggestions


def _parse_value(field: str, value: str, template_fields: dict[str, str]) -> str | None:
    if field == "tc_numero":
        return _parse_tc_numero(value)
    if field == "process_key":
        return _parse_process_key(value)
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
        match = re.search(r"\bTC\s*[\d./-]{3,}\b", text, flags=re.IGNORECASE)
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
    if "data" not in base:
        match = re.search(r"\bDATA\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})", text, flags=re.IGNORECASE)
        if match:
            parsed = _parse_date(match.group(1))
            if parsed:
                base["data"] = {"value": parsed, "confidence": 0.3, "source": "heuristic"}
    if "process_key" not in base:
        match = re.search(r"\bPROC\.?\s*([0-9./*-]+)", text, flags=re.IGNORECASE)
        if match:
            value = _parse_process_key(match.group(1)) or match.group(1)
            base["process_key"] = {"value": value, "confidence": 0.3, "source": "heuristic"}
    if "valor" not in base:
        match = re.search(r"\bVALOR\s*([A-Z$\\s]*[0-9\\.,]+)", text, flags=re.IGNORECASE)
        if match:
            parsed = _parse_decimal(match.group(1))
            if parsed:
                base["valor"] = {"value": parsed, "confidence": 0.3, "source": "heuristic"}
