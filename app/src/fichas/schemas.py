from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class TemplateField(BaseModel):
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: str = "text"
    required: bool = False
    hint: str | None = None

    @field_validator("name", "label", mode="before")
    @classmethod
    def strip_text(cls, v):
        if v is None:
            return v
        v = str(v).strip()
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = {"text", "number", "date"}
        if v not in allowed:
            raise ValueError(f"type must be one of {sorted(allowed)}")
        return v


class BaseProcessFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    process_key: str | None = None
    tc_numero: str | None = None
    ano: int | None = None
    data: date | None = None
    interessado: str | None = None
    assunto: str | None = None
    procedencia: str | None = None
    reparticao: str | None = None
    valor: Decimal | None = None
    observacoes: str | None = None

    @field_validator(
        "process_key",
        "tc_numero",
        "interessado",
        "assunto",
        "procedencia",
        "reparticao",
        "observacoes",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("ano", mode="before")
    @classmethod
    def parse_ano(cls, v):
        if v is None or v == "":
            return None
        return int(v)

    @field_validator("valor", mode="before")
    @classmethod
    def parse_valor(cls, v):
        if v is None or v == "":
            return None
        return Decimal(str(v).replace(",", "."))


class ProcessForm(BaseProcessFields):
    @model_validator(mode="after")
    def ensure_key_or_number(self):
        if not self.process_key and not (self.tc_numero and self.ano):
            raise ValueError("process_key ou tc_numero+ano sao obrigatorios")
        return self


class FichaBaseForm(BaseProcessFields):
    pass


class TemplateForm(BaseModel):
    nome: str = Field(min_length=1)
    descricao: str | None = None
    schema_text: str = Field(min_length=2)

    @field_validator("nome", mode="before")
    @classmethod
    def normalize_nome(cls, v):
        return str(v).strip()


class LoginForm(BaseModel):
    email: str
    password: str


class ProcessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    process_key: str | None
    tc_numero: str | None
    ano: int | None
    data: date | None
    interessado: str | None
    assunto: str | None
    procedencia: str | None
    reparticao: str | None
    valor: Decimal | None
    observacoes: str | None
    created_at: datetime
    updated_at: datetime


class FichaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    process_id: uuid.UUID
    template_id: uuid.UUID
    indexador: str | None
    campos_base_json: dict[str, Any]
    extras_json: dict[str, Any] | None
    observacoes: str | None
    created_at: datetime
    updated_at: datetime


def validation_errors_to_dict(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc") or []
        if not loc:
            continue
        key = str(loc[0])
        errors[key] = err.get("msg", "Erro de validacao")
    return errors


def parse_template_schema(schema_text: str) -> list[TemplateField]:
    try:
        payload = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Schema JSON invalido") from exc
    if not isinstance(payload, list):
        raise ValueError("Schema JSON deve ser uma lista")
    fields: list[TemplateField] = []
    for item in payload:
        fields.append(TemplateField.model_validate(item))
    return fields
