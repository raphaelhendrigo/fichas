from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON, TypeDecorator

Base = declarative_base()


class GUID(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


JSONType = JSONB().with_variant(JSON(), "sqlite")


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    audit_logs = relationship("AuditLog", back_populates="user")


class Process(Base):
    __tablename__ = "processes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    process_key = Column(String(100), unique=True, nullable=True)
    tc_numero = Column(String(50), nullable=True)
    ano = Column(Integer, nullable=True)
    data = Column(Date, nullable=True)
    interessado = Column(String(255), nullable=True)
    assunto = Column(Text, nullable=True)
    procedencia = Column(String(255), nullable=True)
    reparticao = Column(String(255), nullable=True)
    valor = Column(Numeric(15, 2), nullable=True)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    fichas = relationship("Ficha", back_populates="process", cascade="all, delete-orphan")


class FichaTemplate(Base):
    __tablename__ = "ficha_templates"
    __table_args__ = (UniqueConstraint("nome", "versao", name="uq_ficha_templates_nome_versao"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    nome = Column(String(150), nullable=False)
    versao = Column(Integer, nullable=False, default=1)
    origem_pdf = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    descricao = Column(Text, nullable=True)
    schema_json = Column(JSONType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    fichas = relationship("Ficha", back_populates="template")


class Ficha(Base):
    __tablename__ = "fichas"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    process_id = Column(GUID(), ForeignKey("processes.id"), nullable=False)
    template_id = Column(GUID(), ForeignKey("ficha_templates.id"), nullable=False)
    template_version = Column(Integer, nullable=False, default=1)
    indexador = Column(String(100), nullable=True)
    campos_base_json = Column(JSONType, nullable=False)
    extras_json = Column(JSONType, nullable=True)
    observacoes = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="ativo")
    created_by_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    process = relationship("Process", back_populates="fichas")
    template = relationship("FichaTemplate", back_populates="fichas")
    attachments = relationship("Attachment", back_populates="ficha", cascade="all, delete-orphan")
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ficha_id = Column(GUID(), ForeignKey("fichas.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    storage_key = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ficha = relationship("Ficha", back_populates="attachments")


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    storage_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")
    ocr_jobs = relationship("OcrJob", back_populates="document", cascade="all, delete-orphan")


class OcrJob(Base):
    __tablename__ = "ocr_jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    template_id = Column(GUID(), ForeignKey("ficha_templates.id"), nullable=True)
    document_id = Column(GUID(), ForeignKey("uploaded_documents.id"), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    extracted_text = Column(Text, nullable=True)
    ocr_raw_json = Column(JSONType, nullable=True)
    field_suggestions_json = Column(JSONType, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    template = relationship("FichaTemplate")
    document = relationship("UploadedDocument", back_populates="ocr_jobs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)
    entity = Column(String(100), nullable=False)
    entity_id = Column(String(36), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    before_json = Column(JSONType, nullable=True)
    after_json = Column(JSONType, nullable=True)

    user = relationship("User", back_populates="audit_logs")


Index("ix_processes_tc_numero", Process.tc_numero)
Index("ix_processes_ano", Process.ano)
Index("ix_processes_interessado", Process.interessado)
Index("ix_processes_assunto", Process.assunto)
Index("ix_fichas_process_id", Ficha.process_id)
Index("ix_fichas_template_id", Ficha.template_id)
Index("ix_fichas_indexador", Ficha.indexador)
Index("ix_fichas_status", Ficha.status)
Index("ix_uploaded_documents_user_id", UploadedDocument.user_id)
Index("ix_ocr_jobs_user_id", OcrJob.user_id)
Index("ix_ocr_jobs_status", OcrJob.status)
Index("ix_ocr_jobs_created_at", OcrJob.created_at)
