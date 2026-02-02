from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from rapidfuzz import fuzz, process

from fichas.schemas import TemplateSchema
from fichas.settings import settings

_OCR_ENGINE = None


def detect_file_type(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "pdf"
    return "image"


def extract_text_from_pdf(path: Path) -> tuple[str, list[Image.Image]]:
    from pypdf import PdfReader
    from pdf2image import convert_from_path

    reader = PdfReader(str(path))
    extracted = []
    for page in reader.pages:
        text = page.extract_text() or ""
        extracted.append(text)
    raw_text = "\n".join(extracted).strip()

    if len(raw_text) >= 40:
        return raw_text, []

    images = convert_from_path(str(path), first_page=1, last_page=1)
    return raw_text, images


def _deskew(gray: np.ndarray) -> np.ndarray:
    import cv2

    inverted = cv2.bitwise_not(gray)
    coords = cv2.findNonZero(inverted)
    if coords is None:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5:
        return gray
    (height, width) = gray.shape
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(image: Image.Image) -> np.ndarray:
    import cv2

    rgb = image.convert("RGB")
    array = np.array(rgb)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    gray = _deskew(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    return thresh


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR

        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=settings.OCR_LANG)
    return _OCR_ENGINE


def run_paddle_ocr(image: np.ndarray) -> list[dict[str, Any]]:
    ocr = _get_ocr_engine()
    try:
        result = ocr.ocr(image, cls=True)
    except TypeError as exc:
        if "cls" not in str(exc):
            raise
        result = ocr.ocr(image)
    items: list[dict[str, Any]] = []
    if not result:
        return items
    lines: list[Any] = []
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if _looks_like_line(first):
            lines = list(result)
        else:
            for group in result:
                if not group:
                    continue
                if _looks_like_line(group):
                    lines.append(group)
                elif isinstance(group, (list, tuple)) and group and _looks_like_line(group[0]):
                    lines.extend(group)
    for line in lines:
        if not _looks_like_line(line):
            continue
        text = str(line[1][0])
        conf = float(line[1][1])
        bbox = line[0]
        items.append({"text": text, "confidence": conf, "bbox": bbox})
    return items


def _looks_like_line(item: Any) -> bool:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return False
    box, meta = item[0], item[1]
    if not isinstance(meta, (list, tuple)) or len(meta) < 2:
        return False
    return isinstance(meta[0], (str, bytes))


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
    best_text, score, index = best
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
            if lowered in {"nao", "não", "false", "0", "no"}:
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
