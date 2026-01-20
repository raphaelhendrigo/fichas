from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class TemplateFieldValidation(BaseModel):
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    regex: str | None = None


class TemplateFieldLayout(BaseModel):
    order: int = 0
    placeholder: str | None = None
    help: str | None = None
    width: int | None = None
    subsection: str | None = None

    @field_validator("width")
    @classmethod
    def validate_width(cls, v):
        if v is None:
            return v
        if v < 1 or v > 12:
            raise ValueError("width must be between 1 and 12")
        return v


class TemplateField(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    field_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("id", "name", "field_id"),
        alias="id",
    )
    label: str = Field(min_length=1)
    type: str = "text"
    required: bool = False
    hint: str | None = None
    options: list[str] | None = None
    validations: TemplateFieldValidation | None = None
    layout: TemplateFieldLayout | None = None

    @field_validator("field_id", "label", mode="before")
    @classmethod
    def strip_text(cls, v):
        if v is None:
            return v
        v = str(v).strip()
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = {"text", "textarea", "number", "date", "boolean", "enum", "currency"}
        if v not in allowed:
            raise ValueError(f"type must be one of {sorted(allowed)}")
        return v

    @model_validator(mode="after")
    def validate_options(self):
        if self.type == "enum" and not self.options:
            raise ValueError("options is required when type is enum")
        return self


class TemplateSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    section_id: str = Field(min_length=1, validation_alias=AliasChoices("id", "section_id"), alias="id")
    label: str = Field(min_length=1)
    order: int = 0
    description: str | None = None
    fields: list[TemplateField] = Field(default_factory=list)

    @field_validator("section_id", "label", mode="before")
    @classmethod
    def strip_text(cls, v):
        if v is None:
            return v
        v = str(v).strip()
        return v


class TemplateSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sections: list[TemplateSection] = Field(default_factory=list)


class TemplateDraft(TemplateSchema):
    model_config = ConfigDict(extra="ignore")

    nome: str = Field(min_length=1)
    descricao: str | None = None
    versao: int | None = None
    origem_pdf: str | None = None
    is_active: bool = True


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
    origem_pdf: str | None = None
    versao: int | None = None
    is_active: bool = True
    schema_text: str = Field(min_length=2)

    @field_validator("nome", mode="before")
    @classmethod
    def normalize_nome(cls, v):
        if v is None:
            return v
        return str(v).strip()

    @field_validator("origem_pdf", mode="before")
    @classmethod
    def normalize_origem(cls, v):
        if v is None:
            return None
        value = str(v).strip()
        return value or None

    @field_validator("versao", mode="before")
    @classmethod
    def parse_versao(cls, v):
        if v is None or v == "":
            return None
        versao = int(v)
        if versao < 1:
            raise ValueError("Versao deve ser >= 1")
        return versao


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
    template_version: int
    indexador: str | None
    campos_base_json: dict[str, Any]
    extras_json: dict[str, Any] | None
    observacoes: str | None
    status: str
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


def parse_template_schema(schema_text: str) -> TemplateSchema:
    try:
        payload = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Schema JSON invalido") from exc
    try:
        return normalize_template_schema(payload)
    except ValidationError as exc:
        raise ValueError("Schema JSON invalido") from exc


def normalize_template_schema(payload: Any) -> TemplateSchema:
    if isinstance(payload, list):
        fields = [TemplateField.model_validate(item) for item in payload]
        return TemplateSchema(
            sections=[
                TemplateSection(
                    section_id="geral",
                    label="Geral",
                    order=1,
                    fields=fields,
                )
            ]
        )
    if isinstance(payload, dict):
        if "sections" in payload:
            return TemplateSchema.model_validate(payload)
    raise ValueError("Schema JSON deve ser uma lista ou objeto com sections")


def flatten_template_fields(schema: TemplateSchema) -> list[TemplateField]:
    fields: list[TemplateField] = []
    for section in schema.sections:
        fields.extend(section.fields)
    return fields


def build_template_field_map(schema: TemplateSchema) -> dict[str, TemplateField]:
    return {field.field_id: field for field in flatten_template_fields(schema)}
