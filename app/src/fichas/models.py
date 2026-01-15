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

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    nome = Column(String(150), unique=True, nullable=False)
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
    indexador = Column(String(100), nullable=True)
    campos_base_json = Column(JSONType, nullable=False)
    extras_json = Column(JSONType, nullable=True)
    observacoes = Column(Text, nullable=True)
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
