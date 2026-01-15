"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "processes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("process_key", sa.String(length=100), nullable=True),
        sa.Column("tc_numero", sa.String(length=50), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column("interessado", sa.String(length=255), nullable=True),
        sa.Column("assunto", sa.Text(), nullable=True),
        sa.Column("procedencia", sa.String(length=255), nullable=True),
        sa.Column("reparticao", sa.String(length=255), nullable=True),
        sa.Column("valor", sa.Numeric(15, 2), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("process_key"),
    )
    op.create_index("ix_processes_tc_numero", "processes", ["tc_numero"], unique=False)
    op.create_index("ix_processes_ano", "processes", ["ano"], unique=False)
    op.create_index("ix_processes_interessado", "processes", ["interessado"], unique=False)
    op.create_index("ix_processes_assunto", "processes", ["assunto"], unique=False)

    op.create_table(
        "ficha_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("nome"),
    )

    op.create_table(
        "fichas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("process_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("indexador", sa.String(length=100), nullable=True),
        sa.Column("campos_base_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extras_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["ficha_templates.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_fichas_process_id", "fichas", ["process_id"], unique=False)
    op.create_index("ix_fichas_template_id", "fichas", ["template_id"], unique=False)
    op.create_index("ix_fichas_indexador", "fichas", ["indexador"], unique=False)

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ficha_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ficha_id"], ["fichas.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("attachments")
    op.drop_index("ix_fichas_indexador", table_name="fichas")
    op.drop_index("ix_fichas_template_id", table_name="fichas")
    op.drop_index("ix_fichas_process_id", table_name="fichas")
    op.drop_table("fichas")
    op.drop_table("ficha_templates")
    op.drop_index("ix_processes_assunto", table_name="processes")
    op.drop_index("ix_processes_interessado", table_name="processes")
    op.drop_index("ix_processes_ano", table_name="processes")
    op.drop_index("ix_processes_tc_numero", table_name="processes")
    op.drop_table("processes")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
